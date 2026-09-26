#!/usr/bin/env python3
"""Check stock module imports against a rebuilt kernel and stock peer modules.

modprobe is used only with inspection options; no module is loaded. Matching
symbol CRCs and vermagic are necessary checks, not proof of hardware behavior.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def inspected_symbols(path, option):
    result = subprocess.run(['modprobe', option, str(path)], text=True, capture_output=True)
    if result.returncode and option == '--show-exports':
        sections = subprocess.check_output(['readelf', '--sections', '--wide', str(path)],
                                            text=True)
        if '__ksymtab' not in sections and 'No data available' in result.stderr:
            return {}
    if result.returncode:
        raise RuntimeError(result.stderr)
    return {line.split()[1]: int(line.split()[0], 16) for line in result.stdout.splitlines()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--modules', required=True, type=Path)
    parser.add_argument('--symvers', required=True, type=Path)
    parser.add_argument('--release', required=True)
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    providers = {}
    for line in args.symvers.read_text().splitlines():
        fields = line.split()
        # The kernel-only test deploys no rebuilt .ko files. A matching export
        # in an undeployed build module must not satisfy a runtime dependency.
        if fields[2] == 'vmlinux':
            providers[fields[1]] = {'crc': int(fields[0], 16), 'provider': fields[2]}
    modules = sorted(args.modules.glob('*.ko'))
    if len(modules) != 12:
        raise ValueError('Expected the 12 captured karat vendor modules')
    for path in modules:
        for name, crc in inspected_symbols(path, '--show-exports').items():
            if name in providers and providers[name]['crc'] != crc:
                raise ValueError(f'Conflicting exported symbol {name}')
            providers[name] = {'crc': crc, 'provider': path.name}
    results = []
    for path in modules:
        version = subprocess.check_output(['modinfo', '-F', 'vermagic', str(path)],
                                          text=True).strip()
        expected_version = args.release + ' SMP preempt mod_unload modversions aarch64'
        imports = inspected_symbols(path, '--show-modversions')
        missing, mismatches = [], []
        for name, crc in imports.items():
            found = providers.get(name)
            if not found:
                missing.append(name)
            elif found['crc'] != crc:
                mismatches.append({'symbol': name, 'module_crc': f'0x{crc:08x}',
                                   'provider_crc': f"0x{found['crc']:08x}",
                                   'provider': found['provider']})
        results.append({'module': path.name,
                        'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                        'vermagic': version, 'vermagic_matches': version == expected_version,
                        'import_count': len(imports), 'missing': missing,
                        'crc_mismatches': mismatches})
    passed = all(r['vermagic_matches'] and not r['missing'] and not r['crc_mismatches']
                 for r in results)
    report = {'scope': 'Offline module CRC/vermagic checks; no hardware load test.',
              'symvers_sha256': hashlib.sha256(args.symvers.read_bytes()).hexdigest(),
              'release': args.release, 'passed': passed, 'modules': results}
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': passed, 'modules': len(results),
                      'imports': sum(r['import_count'] for r in results),
                      'missing': sum(len(r['missing']) for r in results),
                      'crc_mismatches': sum(len(r['crc_mismatches']) for r in results)}))
    raise SystemExit(not passed)


if __name__ == '__main__':
    main()
