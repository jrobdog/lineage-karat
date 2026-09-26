#!/usr/bin/env python3
"""Check a raw ext4 system image against the captured karat partition budget.

Passing establishes image format and available space only. It does not establish
bootability, SELinux/VINTF/AVB compatibility, or permission to flash the device.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct


def inspect(path, metadata):
    partitions = {p['name']: p for p in metadata['partitions']}
    if set(partitions) != {'system', 'vendor', 'product'}:
        raise ValueError('Unexpected partition set')
    system = partitions['system']
    group = next(g for g in metadata['groups'] if g['name'] == system['group'])
    retained = sum(p['size'] for p in partitions.values()
                   if p['name'] != 'system' and p['group'] == group['name'])
    limit = group['maximum_size'] - retained
    size = path.stat().st_size
    with path.open('rb') as image:
        header = image.read(4)
        if header == bytes.fromhex('3aff26ed'):
            raise ValueError('Android sparse input: unsparse before checking logical size')
        image.seek(1024)
        sb = image.read(1024)
    if len(sb) != 1024 or sb[56:58] != b'\x53\xef':
        raise ValueError('Candidate is not a raw ext4 filesystem')
    if struct.unpack_from('<I', sb, 24)[0] != 2:
        raise ValueError('Expected 4096-byte ext4 blocks for this target')
    block_size = 4096
    blocks = struct.unpack_from('<I', sb, 4)[0]
    incompat = struct.unpack_from('<I', sb, 96)[0]
    if incompat & 0x80:
        blocks |= struct.unpack_from('<I', sb, 336)[0] << 32
    if blocks * block_size > size:
        raise ValueError('Filesystem extends beyond image')
    if size > limit:
        raise ValueError(f'Image {size} bytes exceeds {limit}-byte system budget')
    with path.open('rb') as image:
        digest = hashlib.sha256()
        for chunk in iter(lambda: image.read(1024 * 1024), b''):
            digest.update(chunk)
    return {'image': str(path), 'bytes': size, 'filesystem_bytes': blocks * block_size,
            'sha256': digest.hexdigest(), 'maximum_system_bytes': limit,
            'stock_system_bytes': system['size'],
            'requires_logical_partition_resize': size > system['size'],
            'format_and_size_pass': True, 'boot_tested': False, 'flash_ready': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--metadata', type=Path, default=Path('reports/stock-super.json'))
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = inspect(args.image, json.loads(args.metadata.read_text()))
    encoded = json.dumps(report, indent=2) + '\n'
    if args.output:
        args.output.write_text(encoded)
    print(encoded, end='')


if __name__ == '__main__':
    main()
