#!/usr/bin/env python3
"""Compare effective hardware-domain allow rules using the SETools Python API.

Run in the separate audit container. No policy is loaded into a kernel. This
checks type permissions, not runtime labels, ioctl ranges, or hardware behavior.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import setools

DOMAINS = [
    'hal_tv_cec_default', 'mtk_hal_audio', 'hal_graphics_composer_default',
    'hal_graphics_allocator_default', 'mtk_hal_c2', 'hal_keymaster_default',
    'mtk_hal_keymanage', 'mtk_hal_hdmi', 'mtk_hal_wifi', 'hal_wifi_default',
    'hal_bluetooth_default', 'mtk_hal_bluetooth', 'surfaceflinger',
    'system_server', 'audioserver', 'mediacodec',
]
CLASSES = {'chr_file', 'blk_file', 'binder', 'hwservice_manager', 'service_manager',
           'unix_stream_socket', 'fd', 'file', 'dir', 'property_service'}


def effective(policy, domain):
    result = defaultdict(set)
    query = setools.TERuleQuery(policy, ruletype=['allow'], source=domain,
                               source_indirect=True)
    for rule in query.results():
        if str(rule.tclass) not in CLASSES:
            continue
        for target in rule.target.expand():
            # SELinux "self" is relative to the concrete source domain.
            name = domain if str(target) == 'self' else str(target)
            result[(name, str(rule.tclass))].update(rule.perms)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--after', type=Path, required=True)
    args = parser.parse_args()
    before, after = setools.SELinuxPolicy(str(args.before)), setools.SELinuxPolicy(str(args.after))
    results = []
    for domain in DOMAINS:
        old, new = effective(before, domain), effective(after, domain)
        changes = {'domain': domain, 'lost': [], 'gained': []}
        for key in sorted(old.keys() | new.keys()):
            for name, difference in [('lost', old[key] - new[key]),
                                     ('gained', new[key] - old[key])]:
                if difference:
                    changes[name].append({'target': key[0], 'class': key[1],
                                          'permissions': sorted(difference)})
        results.append(changes)
    print(json.dumps({
        'scope': 'Offline effective allow rules for hardware domains; runtime labels and ioctl ranges remain untested.',
        'before_sha256': hashlib.sha256(args.before.read_bytes()).hexdigest(),
        'after_sha256': hashlib.sha256(args.after.read_bytes()).hexdigest(),
        'classes': sorted(CLASSES), 'domains': results,
    }, indent=2))


if __name__ == '__main__':
    main()
