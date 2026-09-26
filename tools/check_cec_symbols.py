#!/usr/bin/env python3
"""Compare CEC imports with the ARM VNDK30 snapshot used by the build.

This is a limited static check, not a complete ABI or linker-namespace test.
The snapshot's shared/ directory must contain vndk-core/ and vndk-sp/.
"""
import argparse
from functools import lru_cache
import json
from pathlib import Path
import subprocess


@lru_cache(maxsize=None)
def symbols(path):
    result = subprocess.run(['readelf', '--dyn-syms', '--wide', str(path)],
                            capture_output=True, text=True, check=True)
    defined, undefined = set(), set()
    for line in result.stdout.splitlines():
        columns = line.split()
        if len(columns) < 8 or not columns[0].rstrip(':').isdigit():
            continue
        name = columns[7].split('@')[0]
        if columns[6] == 'UND':
            undefined.add(name)
        elif columns[4] in ('GLOBAL', 'WEAK'):
            defined.add(name)
    return defined, undefined


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--stock', type=Path, default=Path('stock/files'))
    parser.add_argument('--inventory', type=Path, default=Path('reports/stock-interfaces.json'))
    parser.add_argument('--output', type=Path, default=Path('reports/cec-vndk30-symbol-check.json'))
    args = parser.parse_args()
    base_libraries = list(args.snapshot.rglob('libhidlbase.so'))
    if len(base_libraries) != 1 or base_libraries[0].read_bytes()[:5] != b'\x7fELF\x01':
        raise ValueError('Expected the ARM VNDK30 shared library snapshot')
    elfs = json.loads(args.inventory.read_text())['elfs']
    blobs = ['vendor/bin/hw/android.hardware.tv.cec@1.0-service-mediatek',
             'vendor/lib/hw/android.hardware.tv.cec@1.0-impl-mediatek.so',
             'vendor/lib/hw/hdmi_cec.mt8696.so']
    checks = []
    for name in blobs:
        elf = next(e for e in elfs if e['path'] == name)
        undefined = symbols(args.stock / name)[1]
        checked, missing = [], {}
        for needed in elf['needed']:
            original = args.stock / 'system/system/apex/com.android.vndk.current/lib' / needed
            matches = sorted(args.snapshot.rglob(needed))
            if not original.is_file() or not matches:
                continue
            used = undefined & symbols(original)[0]
            absent = used - symbols(matches[0])[0]
            checked.append({'library': needed, 'used_symbols': len(used),
                            'missing_symbols': sorted(absent)})
            if absent:
                missing[needed] = sorted(absent)
        checks.append({'blob': name, 'vndk_libraries_checked': checked,
                       'potential_abi_breaks': missing})
    report = {'checks': checks,
              'scope': 'DT_NEEDED libraries present in both stock VNDK and AOSP VNDK30 ARM snapshot only. Does not validate function layouts, linker namespaces, dlopen or runtime behavior.'}
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    count = sum(len(symbols) for entry in checks for symbols in entry['potential_abi_breaks'].values())
    print(f'Checked {len(checks)} CEC binaries; {count} missing symbol matches in the compared VNDK libraries')


if __name__ == '__main__':
    main()
