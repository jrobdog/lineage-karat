#!/usr/bin/env python3
"""Correct the captured headless system's GSI ADB override, entirely offline.

Change the property in its existing ext4 data block, preserving all inode
metadata. Optionally enable the missing Bluetooth remote profile. Regenerate
and verify the development AVB tree/footer. No ADB calls.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

SOURCE_SHA = '417756da7fb4100a2b27a4141e1bb5518b6cf5c07aacf97004267a23b1006988'
IMAGE_BYTES = 1207132160
FILESYSTEM_BYTES = 1188003840
INTERNAL = '/system/system_ext/etc/build.prop'
OLD = b'ro.adb.secure=0\n'
NEW = b'ro.adb.secure=1\n'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run(args):
    result = subprocess.run(list(map(str, args)), capture_output=True, timeout=180)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace'))
    return result.stdout


def debug(image, command):
    return run(['debugfs', '-R', command, image])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system', required=True, type=Path)
    parser.add_argument('--avbtool', required=True, type=Path)
    parser.add_argument('--development-key', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--enable-hid-host', action='store_true')
    args = parser.parse_args()
    if args.system.stat().st_size != IMAGE_BYTES or digest(args.system) != SOURCE_SHA:
        raise ValueError('Require the exact first headless system candidate')
    content = debug(args.system, 'cat ' + INTERNAL)
    if content.count(OLD) != 1 or content.count(b'ro.adb.secure=') != 1:
        raise ValueError('Expected exactly one insecure GSI override')
    corrected = content.replace(OLD, NEW)
    if args.enable_hid_host:
        old_comment = b'# GSI always disables adb authentication\n'
        hid_property = b'bluetooth.profile.hid.host.enabled=true'
        if corrected.count(old_comment) != 1 or b'bluetooth.profile.hid.host.enabled=' in corrected:
            raise ValueError('Unexpected existing Bluetooth profile configuration')
        if len(hid_property) + 1 > len(old_comment):
            raise ValueError('Property does not fit the existing comment line')
        replacement = hid_property.ljust(len(old_comment) - 1, b' ') + b'\n'
        corrected = corrected.replace(old_comment, replacement)
    if len(corrected) != len(content):
        raise ValueError('Property file size changed')
    metadata = debug(args.system, 'stat ' + INTERNAL)
    if not re.search(rb'Type: regular\s+Mode:\s+0644', metadata):
        raise ValueError('Unexpected source metadata')
    blocks = debug(args.system, 'blocks ' + INTERNAL).split()
    if len(blocks) != 1 or not blocks[0].isdigit() or len(content) > 4096:
        raise ValueError('Expected one ordinary ext4 data block')
    offset = int(blocks[0]) * 4096
    with args.system.open('rb') as stream:
        stream.seek(offset)
        if stream.read(len(content)) != content:
            raise ValueError('Logical file does not match the physical block')
    expected_differences = [offset + i for i, (a, b) in enumerate(zip(content, corrected)) if a != b]
    args.out.mkdir(mode=0o700, parents=True, exist_ok=False)
    image = args.out / 'system.img'
    shutil.copyfile(args.system, image)
    avb = [sys.executable, args.avbtool]
    run([*avb, 'erase_footer', '--image', image])
    if image.stat().st_size != FILESYSTEM_BYTES:
        raise ValueError('Unexpected filesystem size after removing footer')
    with image.open('r+b') as stream:
        stream.seek(offset)
        if stream.read(len(content)) != content:
            raise ValueError('Unexpected bytes at property file offset')
        stream.seek(offset)
        stream.write(corrected)
    if debug(image, 'cat ' + INTERNAL) != corrected:
        raise ValueError('Property read-back failed')
    if debug(image, 'stat ' + INTERNAL) != metadata:
        raise ValueError('File metadata changed')
    differences = []
    position = 0
    with args.system.open('rb') as before, image.open('rb') as after:
        while position < FILESYSTEM_BYTES:
            count = min(4 * 1024**2, FILESYSTEM_BYTES - position)
            a, b = before.read(count), after.read(count)
            if len(a) != count or len(b) != count:
                raise ValueError('Truncated filesystem')
            if a != b:
                differences.extend(position + i for i, (x, y) in enumerate(zip(a, b)) if x != y)
            position += count
    if differences != expected_differences:
        raise ValueError('Unexpected filesystem changes')
    (args.out / 'e2fsck.txt').write_bytes(run(['e2fsck', '-f', '-n', image]))
    run([*avb, 'add_hashtree_footer', '--image', image, '--partition_name', 'system',
         '--partition_size', IMAGE_BYTES, '--hash_algorithm', 'sha256',
         '--algorithm', 'SHA256_RSA2048', '--key', args.development_key,
         '--rollback_index', '1769904000', '--do_not_generate_fec',
         '--salt', '3bc68d98ccb6f6e20e8ab29a4ebab37f56e867fe4cf9567d0a2ab441d1aa65b9',
         '--prop', 'com.android.build.system.os_version:13',
         '--prop', 'com.android.build.system.fingerprint:Amazon/lineage_karat/karat:13/TQ3A.230901.001/karat-builder09150245:userdebug/test-keys',
         '--prop', 'com.android.build.system.security_patch:2026-02-01'])
    (args.out / 'avb-info.txt').write_bytes(run([*avb, 'info_image', '--image', image]))
    (args.out / 'avb-verify.txt').write_bytes(run([*avb, 'verify_image', '--image', image,
                                               '--key', args.development_key]))
    if image.stat().st_size != IMAGE_BYTES or digest(args.system) != SOURCE_SHA:
        raise ValueError('Image size or original source changed')
    report = {'scope': 'Offline ADB authentication correction; no device write',
              'source_sha256': SOURCE_SHA, 'image': str(image),
              'sha256': digest(image), 'bytes': IMAGE_BYTES,
              'changed_file': INTERNAL, 'changed_filesystem_bytes': differences,
              'bluetooth_hid_host_enabled': args.enable_hid_host,
              'inode_metadata_unchanged': True, 'filesystem_check': 'passed',
              'avb_self_verification': 'passed', 'fec': False,
              'development_key_is_public_aosp_test_key': True,
              'runtime_authentication_verified': False}
    (args.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
