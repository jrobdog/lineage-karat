#!/usr/bin/env python3
"""Verify the captured firmware and prepare an offline analysis directory.

Uses only local files. No ADB, fastboot, mount, or device writes are performed.
The output must be new; --verify-only is safe to repeat on the original backup.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from extract_super import extract, read_metadata

PROJECT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('backup', type=Path)
    parser.add_argument('--output', type=Path, default=PROJECT / 'stock')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    expected = json.loads((PROJECT / 'reports/firmware-inputs.json').read_text())
    for record in expected['files']:
        path = args.backup / record['file']
        if path.stat().st_size != record['bytes']:
            raise ValueError(f'Unexpected size: {path.name}')
        digest = hashlib.sha256()
        with path.open('rb') as image:
            for chunk in iter(lambda: image.read(1024 * 1024), b''):
                digest.update(chunk)
        if digest.hexdigest() != record['sha256']:
            raise ValueError(f'Firmware hash mismatch: {path.name}')
        print('Verified', path.name)
    if args.verify_only:
        return
    output = args.output.resolve()
    if output.exists():
        raise ValueError('Output already exists; select a new analysis directory')
    output.mkdir(parents=True, mode=0o700)
    metadata = read_metadata(args.backup / 'super.img')
    extract(args.backup / 'super.img', output / 'images', metadata)
    (output / 'super-manifest.json').write_text(json.dumps(metadata, indent=2) + '\n')
    with (output / 'boot-info.txt').open('w') as log:
        subprocess.run([sys.executable, str(PROJECT / 'tools/aosp_unpack_bootimg.py'),
                        '--boot_img', str(args.backup / 'boot.img'),
                        '--out', str(output / 'boot')], stdout=log, check=True)
    print('Prepared', output)
    print('Use debugfs rdump for file analysis; its output does not preserve all image metadata.')


if __name__ == '__main__':
    main()
