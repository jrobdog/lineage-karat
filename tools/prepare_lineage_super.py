#!/usr/bin/env python3
"""Prepare a raw karat super image offline without altering partition geometry.

Clone the verified pre-Lineage backup, replace only system/vendor extents, and
zero any unused space at the end of those logical partitions. Product, metadata
copies, and all unallocated bytes must remain identical. No device operations.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from check_candidate import inspect
from extract_super import read_metadata

BACKUP_SHA256 = 'e4350fe091c7edba129d3228afd9fadae76bfbb51de73a0f6e32a5fc90097b52'
SUPER_BYTES = 1625292800
CHUNK = 4 * 1024 * 1024


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_partition(stream, partition):
    for extent in partition['extents']:
        if extent['kind'] != 0:
            raise ValueError('The captured karat layout must have linear extents only')
        stream.seek(extent['physical_sector'] * 512)
        left = extent['sectors'] * 512
        while left:
            data = stream.read(min(CHUNK, left))
            if not data:
                raise ValueError('Truncated super image')
            left -= len(data)
            yield data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup-super', type=Path, required=True)
    parser.add_argument('--system', type=Path, required=True)
    parser.add_argument('--vendor', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    for source in [args.backup_super, args.system, args.vendor]:
        if not source.is_file():
            raise ValueError('All inputs must be regular image files')
    if args.backup_super.stat().st_size != SUPER_BYTES or digest(args.backup_super) != BACKUP_SHA256:
        raise ValueError('Require the exact verified pre-Lineage super backup')
    metadata = read_metadata(args.backup_super)
    partitions = {p['name']: p for p in metadata['partitions']}
    check = inspect(args.system, metadata)
    if check['requires_logical_partition_resize']:
        raise ValueError('This tool never resizes a logical partition')
    if args.vendor.stat().st_size != partitions['vendor']['size']:
        raise ValueError('Vendor image size differs from the captured partition')
    args.out.mkdir(parents=True, exist_ok=False, mode=0o700)
    image = args.out / 'super.img'
    shutil.copyfile(args.backup_super, image)
    changed_ranges = []
    replacements = {}
    with image.open('r+b') as target:
        for name, source in [('system', args.system), ('vendor', args.vendor)]:
            partition = partitions[name]
            expected_hash = hashlib.sha256()
            with source.open('rb') as stream:
                left_input = source.stat().st_size
                for extent in partition['extents']:
                    if extent['kind'] != 0:
                        raise ValueError('Unexpected non-linear extent')
                    offset, length = extent['physical_sector'] * 512, extent['sectors'] * 512
                    target.seek(offset)
                    changed_ranges.append((offset, offset + length))
                    left_extent = length
                    while left_extent:
                        count = min(CHUNK, left_extent)
                        read_count = min(count, left_input)
                        data = stream.read(read_count)
                        if len(data) != read_count:
                            raise ValueError('Truncated replacement image')
                        left_input -= len(data)
                        data += bytes(count - len(data))
                        if target.write(data) != count:
                            raise ValueError('Incomplete image write')
                        expected_hash.update(data)
                        left_extent -= count
                if left_input or stream.read(1):
                    raise ValueError('Replacement did not fit its partition')
            replacements[name] = {'source_bytes': source.stat().st_size,
                'source_sha256': digest(source), 'logical_bytes': partition['size'],
                'logical_sha256': expected_hash.hexdigest(),
                'zero_padding_bytes': partition['size'] - source.stat().st_size}
        target.flush()
    # Reparse both metadata copies and prove the layout is unchanged.
    new_metadata = read_metadata(image)
    for key in metadata:
        if key != 'source' and metadata[key] != new_metadata[key]:
            raise ValueError(f'Super geometry/metadata changed: {key}')
    with image.open('rb') as target, args.backup_super.open('rb') as original:
        for name, partition in partitions.items():
            actual = hashlib.sha256()
            for data in read_partition(target, partition):
                actual.update(data)
            if name in replacements:
                if actual.hexdigest() != replacements[name]['logical_sha256']:
                    raise ValueError(f'Logical read-back failed: {name}')
            else:
                expected = hashlib.sha256()
                for data in read_partition(original, partition):
                    expected.update(data)
                if actual.digest() != expected.digest():
                    raise ValueError(f'Retained partition changed: {name}')
        # Check every byte outside the replaced ranges, including metadata and
        # unused space; preserving just a decoded metadata object is not enough.
        position = 0
        unchanged = 0
        for start, end in sorted(changed_ranges) + [(SUPER_BYTES, SUPER_BYTES)]:
            original.seek(position)
            target.seek(position)
            while position < start:
                count = min(CHUNK, start - position)
                if original.read(count) != target.read(count):
                    raise ValueError('A byte outside system/vendor extents changed')
                position += count
                unchanged += count
            position = end
    if image.stat().st_size != SUPER_BYTES or digest(args.backup_super) != BACKUP_SHA256:
        raise ValueError('Backup or output size changed')
    report = {'scope': 'Offline super image preparation; no device write or reset',
              'bytes': SUPER_BYTES, 'sha256': digest(image), 'backup_sha256': BACKUP_SHA256,
              'replacements': replacements, 'partition_layout_unchanged': True,
              'all_bytes_outside_replacement_extents_unchanged': True,
              'unchanged_bytes_checked': unchanged, 'stock_product_retained': True,
              'requires_logical_partition_resize': False, 'boot_tested': False,
              'installation_requires_separate_data_migration_authorization': True}
    (args.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
