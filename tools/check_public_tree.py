#!/usr/bin/env python3
"""Check the reviewed source allowlist and basic publication privacy constraints.

This complements a dedicated secret scanner; it cannot prove arbitrary text is
safe. In a Git checkout, only tracked paths are considered. Outside Git, every
file is considered. The allowlist must be reviewed when adding source files.
"""
import json
from pathlib import Path
import re
import subprocess


def main():
    root = Path(__file__).resolve().parents[1]
    allowed = set(json.loads((root / 'PUBLIC_FILES.json').read_text()))
    if (root / '.git').exists():
        result = subprocess.run(['git', 'ls-files', '-z'], cwd=root,
                                check=True, capture_output=True)
        paths = set(result.stdout.decode().rstrip('\0').split('\0'))
    else:
        paths = {p.relative_to(root).as_posix() for p in root.rglob('*')
                 if p.is_file() or p.is_symlink()}
    errors = []
    if paths != allowed:
        errors.append({'unapproved': sorted(paths - allowed),
                       'missing': sorted(allowed - paths)})
    patterns = {
        'private_key_block': r'-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----',
        'home_directory': r'/home/[A-Za-z0-9_.-]+/',
        'private_ipv4': r'\b(?:192\.168|10\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b',
        'device_serial': r'\bG0[A-Z0-9]{12,22}\b',
        'mac_address': r'\b(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b',
    }
    for name in sorted(paths & allowed):
        path = root / name
        if path.is_symlink() or not path.is_file():
            errors.append({'path': name, 'problem': 'Not a regular file'})
            continue
        data = path.read_bytes()
        if len(data) > 2 * 1024 * 1024 or b'\0' in data:
            errors.append({'path': name, 'problem': 'Binary or unexpectedly large file'})
            continue
        try:
            text = data.decode('utf-8')
        except UnicodeDecodeError:
            errors.append({'path': name, 'problem': 'Not UTF-8 source'})
            continue
        for label, pattern in patterns.items():
            if re.search(pattern, text):
                # Report the category and file only, never the matching value.
                errors.append({'path': name, 'problem': label})
    if errors:
        print(json.dumps({'passed': False, 'errors': errors}, indent=2))
        raise SystemExit(1)
    print(json.dumps({'passed': True, 'reviewed_files': len(paths)}))


if __name__ == '__main__':
    main()
