#!/usr/bin/env python3
"""List all Android kernel config mismatches, including active conditions.

This is a diagnostic companion to checkvintf, not a replacement for it. Inputs
are the captured/generated kernel .config and pinned kernel/configs sources.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET


def read_config(path):
    result = {}
    for line in path.read_text().splitlines():
        match = re.fullmatch(r'(CONFIG_\w+)=(.*)', line)
        unset = re.fullmatch(r'# (CONFIG_\w+) is not set', line)
        if match:
            result[match[1]] = match[2]
        elif unset:
            result[unset[1]] = 'n'
    return result


def xml_config(element):
    key, value = element.findtext('key'), element.find('value')
    if value.get('type') != 'bool':
        raise ValueError(f'Unsupported conditional value: {ET.tostring(element)}')
    return key, value.text.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--requirements', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    actual = read_config(args.config)
    base = args.requirements / 'android-base.config'
    conditional = args.requirements / 'android-base-conditional.xml'
    required = read_config(base)
    root = ET.fromstring('<requirements>' + conditional.read_text() + '</requirements>')
    groups = []
    for group in root.findall('group'):
        conditions = dict(xml_config(c) for c in group.findall('conditions/config'))
        active = all(actual.get(k, 'n') == v for k, v in conditions.items())
        groups.append({'conditions': conditions, 'active': active})
        if active:
            for key, value in map(xml_config, group.findall('config')):
                if key in required and required[key] != value:
                    raise ValueError(f'Contradictory requirements for {key}')
                required[key] = value
    mismatches = [{'key': k, 'required': v, 'actual': actual.get(k, 'n')}
                  for k, v in sorted(required.items()) if actual.get(k, 'n') != v]
    report = {
        'scope': 'Offline config source audit; run checkvintf on the built result too.',
        'inputs': {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in [args.config, base, conditional]},
        'required_options': len(required), 'conditional_groups': groups,
        'mismatches': mismatches, 'passed': not mismatches,
    }
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'required_options': len(required), 'mismatches': mismatches}, indent=2))
    raise SystemExit(bool(mismatches))


if __name__ == '__main__':
    main()
