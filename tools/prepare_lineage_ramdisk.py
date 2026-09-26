#!/usr/bin/env python3
"""Patch the captured karat first-stage mounts offline, preserving cpio metadata.

Use with the proven stock kernel for the initial Lineage system experiment.
Only the two fstab files change: system/vendor mount without dm-verity, and
the obsolete product mount is skipped. Data/metadata encryption is untouched.
This is for the already-unlocked development stick, not a locked release image.
"""
import argparse
import difflib
import gzip
import hashlib
import json
from pathlib import Path
import re
import stat

STOCK_SHA256 = '576479c0cef3a1fc590d85a4ffeaac571e63d6c4a35cbfc4ae344f2a1691fe53'
FSTABS = {'fstab.emmc', 'fstab.mt8696'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def unpack(raw):
    """Read newc without extracting or regenerating filesystem metadata."""
    entries = []
    seen = set()
    offset = 0
    while True:
        header = raw[offset:offset + 110]
        if len(header) != 110 or header[:6] != b'070701':
            raise ValueError('Expected a complete newc header')
        fields = [int(header[i:i + 8], 16) for i in range(6, 110, 8)]
        size, namesize = fields[6], fields[11]
        if not 1 <= namesize <= 4096:
            raise ValueError('Invalid cpio name length')
        name_end = offset + 110 + namesize
        name_raw = raw[offset + 110:name_end]
        if len(name_raw) != namesize or name_raw[-1:] != b'\0':
            raise ValueError('Truncated cpio name')
        name = name_raw[:-1].decode('ascii')
        if name in seen or name.startswith('/') or '..' in name.split('/'):
            raise ValueError('Duplicate or unexpected cpio path')
        seen.add(name)
        start = (name_end + 3) & ~3
        end = (start + size + 3) & ~3
        if end > len(raw) or fields[12] != 0:
            raise ValueError('Truncated entry or unexpected checksum')
        entries.append({'name': name, 'header': header, 'fields': fields,
                        'prefix': raw[offset:start], 'data': raw[start:start + size],
                        'raw': raw[offset:end]})
        offset = end
        if name == 'TRAILER!!!':
            if size or any(raw[offset:]):
                raise ValueError('Unexpected data after cpio trailer')
            return entries


def patch_fstab(data):
    lines = []
    seen = set()
    removed = {}
    for line in data.decode('ascii').splitlines(keepends=True):
        if not line.strip() or line.lstrip().startswith('#'):
            lines.append(line)
            continue
        columns = list(re.finditer(r'\S+', line))
        if len(columns) != 5:
            raise ValueError('Unexpected fstab column count')
        values = [m.group() for m in columns]
        device, mountpoint, filesystem, options, flags = values
        if mountpoint not in {'/system', '/vendor', '/product'}:
            lines.append(line)
            continue
        if (mountpoint in seen or device != mountpoint[1:] or filesystem != 'ext4'
                or options != 'ro'):
            raise ValueError('Unexpected logical mount definition')
        seen.add(mountpoint)
        tokens = flags.split(',')
        if not {'wait', 'logical', 'first_stage_mount'} <= set(tokens):
            raise ValueError('Missing required first-stage mount flags')
        if mountpoint == '/product':
            lines.append('# Lineage product is inside /system; retain its stock partition unused.\n')
            removed[mountpoint] = {'mount_skipped': True}
            continue
        drop = [t for t in tokens if t.split('=', 1)[0] in {'avb', 'avb_keys'}]
        if not any(t == 'avb' or t.startswith('avb=') for t in drop):
            raise ValueError('Expected the stock AVB mount flag')
        replacement = ','.join(t for t in tokens if t and t not in drop)
        lines.append(line[:columns[4].start()] + replacement + line[columns[4].end():])
        removed[mountpoint] = {'removed_flags': drop, 'fs_mgr_flags': replacement}
    if seen != {'/system', '/vendor', '/product'}:
        raise ValueError('Missing logical mount in stock fstab')
    return ''.join(lines).encode('ascii'), removed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stock-ramdisk', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    original = args.stock_ramdisk.read_bytes()
    if sha(original) != STOCK_SHA256:
        raise ValueError('Require the exact captured karat ramdisk')
    entries = unpack(gzip.decompress(original))
    if len(entries) != 13 or {e['name'] for e in entries} & FSTABS != FSTABS:
        raise ValueError('Unexpected captured ramdisk inventory')
    chunks, changes, diffs = [], {}, []
    for entry in entries:
        if entry['name'] not in FSTABS:
            chunks.append(entry['raw'])
            continue
        fields = entry['fields']
        if not stat.S_ISREG(fields[1]) or fields[4] != 1:
            raise ValueError('Expected a regular non-hardlinked fstab')
        data, mounts = patch_fstab(entry['data'])
        prefix = bytearray(entry['prefix'])
        prefix[54:62] = f'{len(data):08x}'.encode('ascii')
        chunks.append(bytes(prefix) + data + bytes((-len(data)) % 4))
        changes[entry['name']] = {'before_sha256': sha(entry['data']),
            'after_sha256': sha(data), 'mode': oct(fields[1]), 'uid': fields[2],
            'gid': fields[3], 'mtime': fields[5], 'mounts': mounts}
        diffs.extend(difflib.unified_diff(entry['data'].decode().splitlines(True),
            data.decode().splitlines(True), fromfile='stock/' + entry['name'],
            tofile='lineage/' + entry['name']))
    raw = b''.join(chunks)
    raw += bytes((-len(raw)) % 512)
    result = gzip.compress(raw, mtime=0)
    verified = unpack(gzip.decompress(result))
    if [e['name'] for e in entries] != [e['name'] for e in verified]:
        raise ValueError('Ramdisk inventory changed')
    for before, after in zip(entries, verified):
        if before['name'] not in FSTABS:
            if before['raw'] != after['raw']:
                raise ValueError('An unrelated cpio entry changed')
        else:
            if any(a != b for i, (a, b) in enumerate(zip(before['fields'], after['fields'])) if i != 6):
                raise ValueError('Fstab metadata changed beyond file size')
            for mount in [b'/data', b'/metadata']:
                select = lambda body: [l for l in body.splitlines() if mount in l.split()[1:2]]
                if select(before['data']) != select(after['data']):
                    raise ValueError('Data or metadata mount configuration changed')
    args.out.mkdir(parents=True, exist_ok=False, mode=0o700)
    (args.out / 'ramdisk.gz').write_bytes(result)
    (args.out / 'mounts.diff').write_text(''.join(diffs))
    for entry in verified:
        if entry['name'] in FSTABS:
            (args.out / entry['name']).write_bytes(entry['data'])
    report = {'scope': 'Offline first-stage mount preparation; not a boot result',
              'stock_sha256': sha(original), 'sha256': sha(result), 'bytes': len(result),
              'changes': changes, 'all_other_cpio_entries_byte_identical': True,
              'fstab_metadata_preserved': True, 'data_and_metadata_mounts_unchanged': True,
              'data_migration_authorized_by_this_tool': False,
              'requires_unlocked_device': True, 'selinux_enforcement_unchanged': True,
              'runtime_tested': False}
    (args.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
