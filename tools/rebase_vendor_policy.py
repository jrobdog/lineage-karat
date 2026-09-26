#!/usr/bin/env python3
"""Prepare karat's captured vendor CIL for the pinned LineageOS 20 platform.

Outputs files for offline audit only; does not modify an image or a device.
The current platform supplies its own public rules and type classifications.
Vendor-specific classifications and rules remain, with the reviewed reductions
below. Compile with neverallow checks and audit effective access before use.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

PROPERTY_OWNERSHIP = [
    'amzn_xo_prop', 'devicetype_prop', 'vendor_amzn_audiohal_config_prop',
    'vendor_amzn_drmprov_status_prop', 'vendor_amzn_zigbee_prop',
    'vendor_audio_avsync_tune_prop', 'vendor_audio_config_prop', 'vendor_audio_prop',
    'vendor_debug_service_prop', 'vendor_device_model_prop', 'vendor_fos_flags_wipe_prop',
    'vendor_mtk_fuelgauged_prop', 'vendor_mtk_hdmirx_prop', 'vendor_netflix_prop',
    'vendor_persist_wifi_rssi_prop', 'vendor_touch_gesture_prop',
    'vendor_wifi_hostap_prop', 'wlan_stats_prop',
]
CUSTOM_PUBLIC_TYPES = {'ace_sensorsd', 'amzn_hal_camportal_default', 'i2c_device',
                       'ledcontroller', 'partner_app', 'proc_idme', 'tv_config_file', 'untrustedd'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system', required=True, type=Path)
    parser.add_argument('--vendor-policy', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    paths = [args.system / p for p in [
        'etc/selinux/plat_sepolicy.cil', 'etc/selinux/mapping/30.0.0.cil',
        'etc/selinux/mapping/30.0.0.compat.cil',
        'system_ext/etc/selinux/system_ext_sepolicy.cil',
        'system_ext/etc/selinux/mapping/30.0.0.compat.cil',
    ]]
    extra = args.system / 'system_ext/etc/selinux/mapping/30.0.0.cil'
    if extra.exists():
        paths.append(extra)
    platform = '\n'.join(p.read_text() for p in paths)
    owned_types = set(re.findall(r'^\(type (\w+)\)', platform, re.M))
    owned_attrs = set(re.findall(r'^\(typeattribute (\w+)\)', platform, re.M))
    owned_aliases = set(re.findall(r'^\(typeattributeset (\w+_30_0_0)\b', platform, re.M))
    owned_aliases |= {x for x in owned_attrs if x.endswith('_30_0_0')}
    public_path = args.vendor_policy / 'plat_pub_versioned.cil'
    vendor_path = args.vendor_policy / 'vendor_sepolicy.cil'
    public, vendor = public_path.read_text(), vendor_path.read_text()
    custom = set(re.findall(r'^\(type (\w+)\)', public, re.M)) - owned_types
    if custom != CUSTOM_PUBLIC_TYPES:
        raise ValueError('Unexpected platform/vendor types; this rebase needs a new review')
    custom_symbols = custom | {x + '_30_0_0' for x in custom}
    removed_public = Counter()
    pub_lines = []
    for line in public.splitlines():
        match = re.match(r'^\((\w+) (\w+)', line)
        if match:
            kind, name = match.groups()
            if kind in {'allow', 'allowx', 'neverallow', 'neverallowx',
                        'dontaudit', 'dontauditx', 'auditallow'}:
                if not set(re.findall(r'\b\w+\b', line)) & custom_symbols:
                    removed_public[kind] += 1
                    continue
            if kind == 'typeattributeset' and not name.endswith('_30_0_0'):
                members = re.findall(r'\b\w+\b', line[line.index(name) + len(name):])
                if set(members) & {'and', 'or', 'not', 'xor', 'all'}:
                    raise ValueError('Unexpected public attribute expression')
                members = [x for x in members if x.removesuffix('_30_0_0') in custom]
                if not members:
                    removed_public['shared_attribute_assignment'] += 1
                    continue
                line = '(typeattributeset ' + name + ' (' + ' '.join(members) + '))'
        pub_lines.append(line)

    lines, reductions = [], []
    assignment_changes = Counter()
    audio_ban = ('(neverallow mtk_hal_audio domain (tcp_socket (ioctl read write create '
                 'getattr setattr lock relabelfrom relabelto append map bind connect listen '
                 'accept getopt setopt shutdown recvfrom sendto name_bind node_bind name_connect)))')
    if audio_ban not in vendor:
        raise ValueError('Unexpected MediaTek audio policy')
    for line in vendor.splitlines():
        if line == audio_ban:
            continue
        attr = re.match(r'^\(typeattributeset (\w+) \(([^()]*)\)\)$', line)
        if attr and attr[1] in owned_attrs and not attr[1].endswith('_30_0_0'):
            members = attr[2].split()
            keep = [x for x in members if x not in owned_types and x not in owned_aliases]
            assignment_changes[attr[1]] += len(members) - len(keep)
            if not keep:
                continue
            line = '(typeattributeset ' + attr[1] + ' (' + ' '.join(keep) + '))'
        allow = re.fullmatch(r'\(allow (\w+) (\w+) \((\w+) \(([^()]*)\)\)\)', line)
        if allow:
            source, target, tclass, permission_text = allow.groups()
            permissions = permission_text.split()
            reason = None
            if target == 'vendor_default_prop_30_0_0' and source.endswith('_30_0_0'):
                reductions.append({'rule': line, 'reason': 'Remove legacy core reads of untyped vendor properties; typed hardware property rules remain.'})
                continue
            if target == 'crashreport_data_file' and source in {'crashreport', 'system_server_30_0_0'}:
                reductions.append({'rule': line, 'reason': 'The Amazon system crash reporter is absent; Lineage collects its own crashes.'})
                continue
            if source == 'hal_vehicle_default' and target == 'hal_can_bus_hwservice_30_0_0':
                reductions.append({'rule': line, 'reason': 'No vehicle or CAN HAL exists in the captured karat VINTF manifests.'})
                continue
            if source == 'vendor_init_30_0_0' and target == 'exported_system_prop_30_0_0' and tclass == 'property_service':
                reason = 'Exclude private platform properties newly included in the old exported-property mapping.'
                target = 'karat_legacy_exported_system_writable'
            if source in {'hal_audio_default', 'hal_graphics_composer_default'} and target == 'exported_system_prop_30_0_0' and tclass == 'file':
                reason = 'Exclude the private charger-status property introduced after the vendor API.'
                target = 'karat_legacy_exported_system_readable'
            if target == 'proc_net_30_0_0' and tclass == 'file' and 'write' in permissions:
                reason = 'Preserve network-node access while reserving BPF control writes for the platform BPF loader.'
                remainder = [p for p in permissions if p != 'write']
                if remainder:
                    lines.append(f'(allow {source} {target} (file ({" ".join(remainder)})))')
                target, permissions = 'karat_legacy_proc_net_writable', ['write']
            if reason:
                reductions.append({'rule': line, 'reason': reason})
                line = f'(allow {source} {target} ({tclass} ({" ".join(permissions)})))'
        lines.append(line)
    if len(reductions) != 34:
        raise ValueError(f'Expected 34 reviewed legacy rules, found {len(reductions)}')

    # These 18 legacy vendor properties had no modern ownership classification.
    # Ownership attributes do not add allow rules. Existing explicit readers and
    # writers are retained; the complete policy must still pass the strict audit.
    for attr in ['vendor_property_type', 'vendor_public_property_type']:
        lines.append(f'(typeattributeset {attr} ({" ".join(PROPERTY_OWNERSHIP)}))')
    lines.extend([
        '(typeattributeset coredomain (vzwomatrigger_app))',
        '(typeattributeset bpfdomain (charger_vendor hal_health_default))',
        '(typeattributeset system_file_type (read_lifetime_exec))',
        '(typeattribute karat_audio_non_debugger_domain)',
        '(typeattributeset karat_audio_non_debugger_domain (and (domain) (not (su))))',
        '(neverallow mtk_hal_audio karat_audio_non_debugger_domain (tcp_socket (read write accept getopt)))',
        '(neverallow mtk_hal_audio domain (tcp_socket (ioctl create getattr setattr lock relabelfrom relabelto append map bind connect listen setopt shutdown recvfrom sendto name_bind node_bind name_connect)))',
        '(typeattribute karat_legacy_exported_system_writable)',
        '(typeattributeset karat_legacy_exported_system_writable (and (exported_system_prop_30_0_0) (and (system_public_property_type) (not (bootanim_system_prop)))))',
        '(typeattribute karat_legacy_exported_system_readable)',
        '(typeattributeset karat_legacy_exported_system_readable (and (exported_system_prop_30_0_0) (not (charger_status_prop))))',
        '(typeattribute karat_legacy_proc_net_writable)',
        '(typeattributeset karat_legacy_proc_net_writable (and (proc_net_30_0_0) (not (proc_bpf))))',
        # Preserve measured legacy allocator/keymaster IPC needed by vendor code.
        '(typeattributeset hal_allocator_client (surfaceflinger_30_0_0))',
        '(typeattributeset hal_keymaster_client (mediaserver_30_0_0))',
        # The first Android 13 boot left /proc/idme labeled as generic proc.
        # Device identification and audio setup already have narrow proc_idme
        # read rules; restore the missing device-specific label without adding
        # access to generic proc or changing enforcement.
        '(roletype object_r proc_idme)',
        '(genfscon proc /idme (u object_r proc_idme ((s0) (s0))))',
        # Amazon's system_ext supplied this mapping. Lineage has no IDME type,
        # so the retained versioned vendor rules otherwise target an empty
        # attribute even after the /proc/idme label is restored.
        '(typeattributeset proc_idme_30_0_0 (proc_idme))',
    ])
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / public_path.name).write_text('\n'.join(pub_lines) + '\n')
    (args.out / vendor_path.name).write_text('\n'.join(lines) + '\n')
    report = {
        'scope': 'Offline policy preparation, requiring strict compilation and effective-access review before packaging.',
        'platform_policy_modified': False, 'changes_enforcement': False,
        'inputs': {str(p): digest(p) for p in paths + [public_path, vendor_path]},
        'replaced_legacy_public_statements': dict(removed_public),
        'removed_old_platform_memberships': dict(assignment_changes),
        'retained_custom_public_types': sorted(custom), 'classified_properties': PROPERTY_OWNERSHIP,
        'device_genfs_labels': {'proc:/idme': 'u:object_r:proc_idme:s0'},
        'restored_device_type_mappings': {'proc_idme_30_0_0': ['proc_idme']},
        'reviewed_vendor_reductions': reductions,
        'audio_debugger_exception': 'Existing userdebug su descriptors only; create/connect/listen remain forbidden.',
        'output_sha256': {p.name: digest(p) for p in [args.out / public_path.name, args.out / vendor_path.name]},
    }
    (args.out / 'rebase.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'output': str(args.out), 'reviewed_vendor_reductions': len(reductions)}))


if __name__ == '__main__':
    main()
