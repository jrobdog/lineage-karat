#!/usr/bin/env python3
"""Set ADB-only as the retained vendor's USB default; offline image preparation.

The inherited MTP value overrides system defaults during property loading.
Authenticated ADB remains configured in the corrected system_ext image.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys

from prepare_adb_auth_system import debug, digest, run

SOURCE_SHA = 'd46553edecb56f5d48b9656f0905e151bc56f3fcd428f5477e96f5b9d99ff971'
IMAGE_BYTES = 135172096
FILESYSTEM_BYTES = 132952064
INTERNAL = '/default.prop'
OLD = b'persist.sys.usb.config=mtp\n'
NEW = b'persist.sys.usb.config=adb\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vendor', required=True, type=Path)
    parser.add_argument('--avbtool', required=True, type=Path)
    parser.add_argument('--development-key', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    if args.vendor.stat().st_size != IMAGE_BYTES or digest(args.vendor) != SOURCE_SHA:
        raise ValueError('Require the strictly validated IDME-corrected vendor')
    content = debug(args.vendor, 'cat ' + INTERNAL)
    if content.count(OLD) != 1 or content.count(b'persist.sys.usb.config=') != 1:
        raise ValueError('Unexpected vendor USB defaults')
    corrected = content.replace(OLD, NEW)
    metadata = debug(args.vendor, 'stat ' + INTERNAL)
    blocks = debug(args.vendor, 'blocks ' + INTERNAL).split()
    if blocks != [b'1442'] or len(content) != 601 or len(corrected) != len(content):
        raise ValueError('Unexpected property file geometry')
    offset = int(blocks[0]) * 4096
    expected = [offset + i for i, (x, y) in enumerate(zip(content, corrected)) if x != y]
    args.out.mkdir(mode=0o700, parents=True, exist_ok=False)
    image = args.out / 'vendor.img'
    shutil.copyfile(args.vendor, image)
    avb = [sys.executable, args.avbtool]
    run([*avb, 'erase_footer', '--image', image])
    if image.stat().st_size != FILESYSTEM_BYTES:
        raise ValueError('Unexpected filesystem size')
    with image.open('r+b') as stream:
        stream.seek(offset)
        if stream.read(len(content)) != content:
            raise ValueError('Physical block does not match the logical file')
        stream.seek(offset)
        stream.write(corrected)
    if debug(image, 'cat ' + INTERNAL) != corrected or debug(image, 'stat ' + INTERNAL) != metadata:
        raise ValueError('File content or metadata verification failed')
    changed = []
    with args.vendor.open('rb') as a, image.open('rb') as b:
        position = 0
        while position < FILESYSTEM_BYTES:
            count = min(4 * 1024**2, FILESYSTEM_BYTES - position)
            x, y = a.read(count), b.read(count)
            if len(x) != count or len(y) != count:
                raise ValueError('Truncated filesystem')
            if x != y:
                changed.extend(position + i for i, (v, w) in enumerate(zip(x, y)) if v != w)
            position += count
    if changed != expected or len(changed) != 3:
        raise ValueError('Unexpected filesystem changes')
    (args.out / 'e2fsck.txt').write_bytes(run(['e2fsck', '-f', '-n', image]))
    run([*avb, 'add_hashtree_footer', '--image', image, '--partition_name', 'vendor',
         '--partition_size', IMAGE_BYTES, '--hash_algorithm', 'sha256',
         '--algorithm', 'SHA256_RSA2048', '--key', args.development_key,
         '--rollback_index', '0', '--do_not_generate_fec',
         '--salt', '9dc2134d87b5dc30d6cc9d0f3abf5bc05ad68686146ed27894ac7b61927bf6f2'])
    (args.out / 'avb-info.txt').write_bytes(run([*avb, 'info_image', '--image', image]))
    (args.out / 'avb-verify.txt').write_bytes(run([*avb, 'verify_image', '--image', image,
                                               '--key', args.development_key]))
    if image.stat().st_size != IMAGE_BYTES or digest(args.vendor) != SOURCE_SHA:
        raise ValueError('Original source or output size changed')
    report = {'source_sha256': SOURCE_SHA, 'image': str(image), 'sha256': digest(image),
              'bytes': IMAGE_BYTES, 'changed_file': INTERNAL,
              'changed_filesystem_bytes': changed, 'inode_metadata_unchanged': True,
              'filesystem_check': 'passed', 'avb_self_verification': 'passed',
              'scope': 'Offline vendor USB-default correction; no device write',
              'runtime_verified': False}
    (args.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
