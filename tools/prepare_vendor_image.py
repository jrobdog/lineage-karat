#!/usr/bin/env python3
"""Clone unlocked karat vendor with rebased CILs and optional USB/audio fixes.

Accepts regular image files only. It never mounts a filesystem or uses ADB.
The original image is read-only; output must be a new directory. A development
AVB footer is self-checked, but its key is not trusted by Amazon's stock vbmeta.
Use the vendor extents from the verified pre-Lineage backup. This preserves the
unlock's recovery-from-boot.bak rename that prevents restoring stock recovery.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

from prepare_audio_policy import convert as convert_audio_policy

STOCK_SHA256 = '62982976dcdbcdbffdeada21b9049bef3201a1ce6574476c75fc3df9a723e39e'
PARTITION_SIZE = 135172096
POLICIES = ('plat_pub_versioned.cil', 'vendor_sepolicy.cil')
LABEL = b'u:object_r:vendor_configs_file:s0\0'


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def run(command):
    result = subprocess.run(list(map(str, command)), capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f'{command[0]} exited {result.returncode}: {result.stderr}')
    return result.stdout + result.stderr


def debug(image, command, write=False):
    return run(['debugfs', *(['-w'] if write else []), '-R', command, image])


def token(path):
    # debugfs parses its own command language; shell quoting is not sufficient.
    value = str(path)
    if not re.fullmatch(r'[/A-Za-z0-9_.-]+', value):
        raise ValueError(f'Unsupported debugfs path: {value}')
    return value


def metadata(image, path):
    value = debug(image, f'stat {path}')
    if not re.search(r'Type: regular\s+Mode:\s+0644', value):
        raise ValueError(f'Unexpected type/mode: {path}')
    if not re.search(r'User:\s+0\s+Group:\s+0', value):
        raise ValueError(f'Unexpected ownership: {path}')
    if not re.search(r'Links: 1\s', value):
        raise ValueError(f'Unexpected hard links: {path}')
    fields = re.findall(r'\b(ctime|atime|mtime|crtime): (0x[0-9a-f]+):([0-9a-f]+)', value)
    times = {name: seconds for name, seconds, extra in fields}
    if any(int(extra, 16) for name, seconds, extra in fields):
        raise ValueError(f'Unexpected timestamp precision: {path}')
    if any(t != '0x495c0780' for t in times.values()) or len(times) != 4:
        raise ValueError(f'Unexpected timestamps: {path}')
    if len(re.findall(r'^  [a-zA-Z0-9_.]+ \(\d+\) =', value, re.M)) != 1:
        raise ValueError(f'Unexpected extended attributes: {path}')
    return {'mode': '0100644', 'uid': 0, 'gid': 0, 'links': 1, 'times': times}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stock', required=True, type=Path)
    parser.add_argument('--policy-dir', required=True, type=Path)
    parser.add_argument('--avbtool', required=True, type=Path)
    parser.add_argument('--development-key', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--adb-usb-default', action='store_true',
                        help='Keep USB ADB available with the authenticated system image')
    parser.add_argument('--lineage-audio-policy', action='store_true',
                        help='Use the standard engine and remove the unsupported Amazon AVLS branch')
    args = parser.parse_args()
    for path in [args.stock, args.avbtool, args.development_key,
                 *(args.policy_dir / n for n in POLICIES)]:
        if not path.is_file():
            raise ValueError(f'Not a regular file: {path}')
    if digest(args.stock) != STOCK_SHA256 or args.stock.stat().st_size != PARTITION_SIZE:
        raise ValueError('Require the unlocked vendor from the verified pre-Lineage backup')
    root_listing = debug(args.stock, 'ls -l /')
    if 'recovery-from-boot.bak' not in root_listing or 'recovery-from-boot.p' in root_listing:
        raise ValueError('The existing stock-recovery replacement protection is missing')
    args.out.mkdir(parents=True, exist_ok=False, mode=0o700)
    output = args.out.resolve()
    image = output / 'vendor.img'
    shutil.copyfile(args.stock, image)
    avb = [sys.executable, args.avbtool]
    run([*avb, 'erase_footer', '--image', image])
    records = []
    replacements = [('/etc/selinux/' + name, (args.policy_dir / name).resolve())
                    for name in POLICIES]
    if args.lineage_audio_policy:
        # The legacy Bluetooth variant is a separate generic AOSP policy, with
        # neither the custom engine nor AVLS. Preserve it byte-for-byte.
        for name in ('audio_policy_configuration.xml',):
            original = output / ('original-' + name)
            debug(args.stock, f'dump /etc/{name} {token(original)}')
            converted = output / name
            converted.write_bytes(convert_audio_policy(original.read_bytes()))
            replacements.append(('/etc/' + name, converted))
    for internal, source in replacements:
        name = Path(internal).name
        before = metadata(args.stock, internal)
        label = output / (name + '.selinux')
        debug(args.stock, f'ea_get -f {token(label)} {internal} security.selinux')
        if label.read_bytes() != LABEL:
            raise ValueError(f'Unexpected SELinux label: {name}')
        debug(image, f'rm {internal}', write=True)
        debug(image, f'write {token(source)} {internal}', write=True)
        for field, value in [('mode', '0100644'), ('uid', '0'), ('gid', '0'),
                             *before['times'].items()]:
            debug(image, f'set_inode_field {internal} {field} {value}', write=True)
        for field in ['atime_extra', 'mtime_extra', 'ctime_extra', 'crtime_extra']:
            debug(image, f'set_inode_field {internal} {field} 0', write=True)
        debug(image, f'ea_set -f {token(label)} {internal} security.selinux', write=True)
        after = metadata(image, internal)
        check = output / ('verified-' + name)
        debug(image, f'dump {internal} {token(check)}')
        check_label = output / ('verified-' + name + '.selinux')
        debug(image, f'ea_get -f {token(check_label)} {internal} security.selinux')
        if before != after or digest(check) != digest(source) or check_label.read_bytes() != LABEL:
            raise ValueError(f'Written policy/metadata verification failed: {name}')
        records.append({'path': internal, 'sha256': digest(check), 'metadata': after,
                        'selinux_label': LABEL[:-1].decode()})
    if args.adb_usb_default:
        # Same-block, same-length replacement preserves ownership, label, times
        # and every other property. Authentication is configured in system_ext.
        internal = '/default.prop'
        content_path = output / 'original-default.prop'
        debug(image, f'dump {internal} {token(content_path)}')
        content = content_path.read_bytes()
        old, new = b'persist.sys.usb.config=mtp\n', b'persist.sys.usb.config=adb\n'
        if len(content) != 601 or content.count(old) != 1:
            raise ValueError('Unexpected vendor USB defaults')
        before = debug(image, f'stat {internal}')
        if debug(image, f'blocks {internal}').split('debugfs')[0].split() != ['1442']:
            raise ValueError('Unexpected USB property block')
        with image.open('r+b') as stream:
            stream.seek(1442 * 4096)
            if stream.read(len(content)) != content:
                raise ValueError('Property block mismatch')
            stream.seek(1442 * 4096)
            stream.write(content.replace(old, new))
        verified = output / 'verified-default.prop'
        debug(image, f'dump {internal} {token(verified)}')
        if verified.read_bytes() != content.replace(old, new) or debug(image, f'stat {internal}') != before:
            raise ValueError('USB property content or metadata changed unexpectedly')
    (output / 'e2fsck.txt').write_text(run(['e2fsck', '-f', '-n', image]))
    # This fixed development salt makes packaging reproducible. There is no FEC
    # generator on this host; the verity tree and signature are still verified.
    run([*avb, 'add_hashtree_footer', '--image', image, '--partition_name', 'vendor',
         '--partition_size', PARTITION_SIZE, '--hash_algorithm', 'sha256',
         '--algorithm', 'SHA256_RSA2048', '--key', args.development_key,
         '--salt', '9dc2134d87b5dc30d6cc9d0f3abf5bc05ad68686146ed27894ac7b61927bf6f2',
         '--do_not_generate_fec', '--rollback_index', '0'])
    (output / 'avb-info.txt').write_text(run([*avb, 'info_image', '--image', image]))
    (output / 'avb-verify.txt').write_text(run([*avb, 'verify_image', '--image', image,
                                             '--key', args.development_key]))
    if image.stat().st_size != PARTITION_SIZE or digest(args.stock) != STOCK_SHA256:
        raise ValueError('Final partition size or original hash changed')
    if debug(image, 'ls -l /').split('debugfs')[0] != root_listing.split('debugfs')[0]:
        raise ValueError('Vendor root entries changed unexpectedly')
    report = {'scope': 'Offline vendor policy patch; no flash or hardware test.',
              'stock_sha256': STOCK_SHA256, 'image': str(image),
              'bytes': image.stat().st_size, 'sha256': digest(image),
              'replaced_files': records, 'filesystem_read_only_check': 'passed',
              'avb_self_verification': 'passed', 'fec': False,
              'unlocked_recovery_replacement_protection_preserved': True,
              'amazon_key_trust': False, 'development_key_is_public_aosp_test_key': True,
              'usb_default': 'adb' if args.adb_usb_default else 'mtp',
              'lineage_audio_policy': args.lineage_audio_policy,
              'boot_tested': False}
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
