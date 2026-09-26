#!/usr/bin/env python3
"""Inventory extracted stock ELF dependencies and VINTF without executing blobs.

The provider index is a filename/ELF-class inventory, not a linker namespace or
ABI compatibility test. A library found in stock is not necessarily in Lineage.
"""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET


def inspect_elf(item):
    partition, base, path = item
    with path.open('rb') as stream:
        header = stream.read(20)
    if not header.startswith(b'\x7fELF'):
        return None
    result = subprocess.run(['readelf', '-dW', str(path)], capture_output=True,
                            text=True, check=True)
    needed = re.findall(r'\(NEEDED\).*?\[(.*?)\]', result.stdout)
    soname = re.findall(r'\(SONAME\).*?\[(.*?)\]', result.stdout)
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return {'path': partition + '/' + path.relative_to(base).as_posix(),
            'bits': {1: 32, 2: 64}[header[4]],
            'machine': int.from_bytes(header[18:20], 'little'),
            'soname': soname[0] if soname else path.name,
            'needed': needed,
            'sha256': digest.hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stock', type=Path, default=Path('stock/files'))
    parser.add_argument('--output', type=Path, default=Path('reports/stock-interfaces.json'))
    args = parser.parse_args()
    items = []
    for partition in ('system', 'vendor', 'product'):
        base = args.stock / partition
        for path in sorted(base.rglob('*')):
            if path.is_file() and not path.is_symlink():
                items.append((partition, base, path))
    with ThreadPoolExecutor(max_workers=6) as pool:
        elfs = [entry for entry in pool.map(inspect_elf, items) if entry]
    providers = defaultdict(list)
    for elf in elfs:
        providers[(elf['bits'], elf['soname'])].append(elf['path'])
    vendor_dependencies = defaultdict(set)
    for elf in elfs:
        if elf['path'].startswith('vendor/'):
            for name in elf['needed']:
                vendor_dependencies[(elf['bits'], name)].add(elf['path'])
    external = []
    for (bits, name), consumers in sorted(vendor_dependencies.items()):
        matches = providers[(bits, name)]
        if not any(p.startswith('vendor/') for p in matches):
            external.append({'library': name, 'bits': bits,
                             'stock_providers': matches, 'consumers': sorted(consumers)})
    hals = []
    for path in sorted((args.stock / 'vendor/etc/vintf').rglob('*.xml')):
        root = ET.parse(path).getroot()
        if root.tag != 'manifest':
            continue
        for hal in root.findall('hal'):
            hals.append({'source': path.relative_to(args.stock).as_posix(),
                         'name': hal.findtext('name'),
                         'versions': [v.text for v in hal.findall('version')],
                         'fqnames': [v.text for v in hal.findall('fqname')]})
    version = (args.stock / 'vendor/etc/selinux/plat_sepolicy_vers.txt').read_text().strip()
    report = {'elf_count': len(elfs),
              'elf_classes': dict(Counter(str(e['bits']) for e in elfs)),
              'vendor_policy_version': version,
              'vendor_dependencies_outside_vendor': external,
              'hals': hals, 'elfs': elfs,
              'limitations': ['Basename matching does not validate exported symbols or linker namespaces.',
                             'APEX payloads that remain archived are not searched.',
                             'dlopen dependencies are not represented by ELF DT_NEEDED.']}
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'elf_count': len(elfs), 'elf_classes': report['elf_classes'],
                      'external_vendor_dependencies': len(external), 'vendor_policy_version': version}))
    for elf in elfs:
        if 'cec' in elf['path'].lower():
            print(elf['path'], 'needs', ', '.join(elf['needed']))


if __name__ == '__main__':
    main()
