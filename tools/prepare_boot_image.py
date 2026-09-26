#!/usr/bin/env python3
"""Package a test kernel in karat's captured v2 boot layout; no device operations.

Unpacks the result again and checks every unchanged header byte and component.
Requires the kernel's embedded configuration to match the audited .config.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import struct
import sys

from aosp_unpack_bootimg import unpack_boot_image

STOCK_SHA256 = '53aa1c58df16e36697e2b37f119cdfbbe131b2d5ccacb103821ee9ba457b9603'
PARTITION_SIZE = 41943040


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def run(command):
    result = subprocess.run(list(map(str, command)), capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f'{command[0]} exited {result.returncode}: {result.stderr}')
    return result.stdout + result.stderr


def embedded_config(kernel):
    raw = gzip.decompress(kernel.read_bytes())
    marker = b'IKCFG_ST\x1f\x8b\x08'
    if raw.count(marker) != 1:
        raise ValueError('Expected one embedded kernel config')
    start = raw.index(marker) + 8
    end = raw.index(b'IKCFG_ED', start)
    return gzip.decompress(raw[start:end])


def header_v2_id(kernel, ramdisk, dtb):
    """The captured v2 image has no second stage or recovery DTBO.

    Lineage's mkbootimg fork also hashes an empty legacy --dt field, which
    changes this digest. Validate our v2 calculation against the original image
    before using it for any rebuilt component.
    """
    result = hashlib.sha1()
    for data in [kernel, ramdisk, b'', b'', dtb]:
        result.update(data)
        result.update(struct.pack('<I', len(data)))
    return result.digest() + bytes(12)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stock-boot', required=True, type=Path)
    parser.add_argument('--kernel', required=True, type=Path)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--ramdisk', type=Path, help='Explicit optional alternate ramdisk')
    parser.add_argument('--panic-reboot-seconds', type=int,
                        help='Diagnostic boot: request automatic reboot after a kernel panic')
    parser.add_argument('--mkbootimg', required=True, type=Path)
    parser.add_argument('--avbtool', required=True, type=Path)
    parser.add_argument('--development-key', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    if args.panic_reboot_seconds is not None and not 1 <= args.panic_reboot_seconds <= 60:
        raise ValueError('Panic reboot timeout must be 1 to 60 seconds')
    paths = [args.stock_boot, args.kernel, args.config, args.mkbootimg,
             args.avbtool, args.development_key, *([args.ramdisk] if args.ramdisk else [])]
    if any(not p.is_file() for p in paths):
        raise ValueError('All inputs must be regular files')
    if digest(args.stock_boot) != STOCK_SHA256:
        raise ValueError('Expected the verified, captured karat boot image')
    if embedded_config(args.kernel) != args.config.read_bytes():
        raise ValueError('Kernel embedded config does not match the audited configuration')
    args.out.mkdir(parents=True, exist_ok=False, mode=0o700)
    output = args.out.resolve()
    with args.stock_boot.open('rb') as f:
        old = unpack_boot_image(f, str(output / 'original'))
    if (old.header_version != 2 or old.page_size != 2048 or old.boot_header_size != 1660
            or old.second_size or old.recovery_dtbo_size):
        raise ValueError('Unexpected boot geometry')
    original_id = header_v2_id(*(output.joinpath('original', name).read_bytes()
                                for name in ['kernel', 'ramdisk', 'dtb']))
    if args.stock_boot.read_bytes()[576:608] != original_id:
        raise ValueError('The v2 checksum algorithm does not reproduce the stock header ID')
    parameters = old.format_mkbootimg_argument()
    if args.panic_reboot_seconds is not None:
        command_line = parameters.index('--cmdline') + 1
        parameters[command_line] += f' panic={args.panic_reboot_seconds}'
    parameters[parameters.index('--kernel') + 1] = str(args.kernel.resolve())
    ramdisk = args.ramdisk.resolve() if args.ramdisk else output / 'original/ramdisk'
    parameters[parameters.index('--ramdisk') + 1] = str(ramdisk)
    image = output / 'boot.img'
    run([sys.executable, args.mkbootimg, *parameters, '--output', image])
    image_id = header_v2_id(args.kernel.read_bytes(), ramdisk.read_bytes(),
                            (output / 'original/dtb').read_bytes())
    with image.open('r+b') as f:
        f.seek(576)
        f.write(image_id)
    # Only sizes and the boot-header SHA-1 may change. All load addresses,
    # command-line, OS header metadata, page sizes and DTB fields must survive.
    before = args.stock_boot.read_bytes()[:1660]
    after = image.read_bytes()[:1660]
    allowed = set(range(8, 12)) | set(range(576, 608))
    if args.ramdisk:
        allowed |= set(range(16, 20))
    if args.panic_reboot_seconds is not None:
        allowed |= set(range(64, 576)) | set(range(608, 1632))
    changed = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
    if len(after) != 1660 or any(i not in allowed for i in changed):
        raise ValueError(f'Unexpected boot header changes: {changed}')
    avb = [sys.executable, args.avbtool]
    run([*avb, 'add_hash_footer', '--image', image, '--partition_name', 'boot',
         '--partition_size', PARTITION_SIZE, '--hash_algorithm', 'sha256',
         '--algorithm', 'SHA256_RSA2048', '--key', args.development_key,
         '--rollback_index', '2',
         '--salt', '836de5e7b4e1bce46fb558bd80e4e46d6e9e1f00472ab5f81569d7fd8ba17221',
         '--prop', 'com.android.build.boot.fingerprint:Amazon/karat/karat:11/RS8182.3811N/0032548774656:user/amz-p,release-keys',
         '--prop', 'com.android.build.boot.os_version:11',
         '--prop', 'com.android.build.boot.security_patch:2019-06-06'])
    with image.open('rb') as f:
        new = unpack_boot_image(f, str(output / 'verified'))
    for name, source in [('kernel', args.kernel), ('ramdisk', ramdisk),
                         ('dtb', output / 'original/dtb')]:
        if digest(output / 'verified' / name) != digest(source):
            raise ValueError(f'Boot round-trip changed {name}')
    (output / 'boot-info.txt').write_text(new.format_pretty_text() + '\n')
    (output / 'avb-info.txt').write_text(run([*avb, 'info_image', '--image', image]))
    (output / 'avb-verify.txt').write_text(run([*avb, 'verify_image', '--image', image,
                                             '--key', args.development_key]))
    if image.stat().st_size != PARTITION_SIZE or digest(args.stock_boot) != STOCK_SHA256:
        raise ValueError('Partition size or original boot hash changed')
    report = {'scope': 'Packaged test boot image; not a hardware boot result.',
              'image': str(image), 'bytes': image.stat().st_size, 'sha256': digest(image),
              'stock_boot_sha256': STOCK_SHA256, 'kernel_sha256': digest(args.kernel),
              'config_sha256': digest(args.config), 'embedded_config_matches': True,
              'ramdisk_sha256': digest(ramdisk), 'ramdisk_changed': bool(args.ramdisk),
              'diagnostic_panic_reboot_seconds': args.panic_reboot_seconds,
              'dtb_sha256': digest(output / 'verified/dtb'),
              'v2_header_checksum_matches_stock_algorithm': True,
              'unchanged_header_fields_verified': True, 'component_roundtrip': 'passed',
              'avb_self_verification': 'passed', 'amazon_key_trust': False,
              'development_key_is_public_aosp_test_key': True, 'rollback_index': 2,
              'header_os_version_retained_for_hardware_test': '11.0.0',
              'boot_tested': False}
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
