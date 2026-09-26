#!/usr/bin/env python3
"""Compile the candidate's installed split-policy inputs with stock vendor policy.

Runs both the normal Android init flags and a separate strict neverallow audit.
All output stays in a new report directory. This does not load a kernel policy,
change enforcement, execute vendor code, or test a boot.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system', type=Path, required=True)
    parser.add_argument('--stock-policy', type=Path, required=True)
    parser.add_argument('--secilc', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    system = args.system / 'etc/selinux'
    ext = args.system / 'system_ext/etc/selinux'
    product = args.system / 'product/etc/selinux'
    required = [system / 'plat_sepolicy.cil', system / 'mapping/30.0.0.cil',
                args.stock_policy / 'vendor/plat_pub_versioned.cil',
                args.stock_policy / 'vendor/vendor_sepolicy.cil']
    for path in required:
        if not path.is_file():
            raise SystemExit(f'Required policy input missing: {path}')
    # Match normal split-policy input selection in the pinned system/core init.
    optional = [system / 'mapping/30.0.0.compat.cil',
                ext / 'system_ext_sepolicy.cil', ext / 'mapping/30.0.0.cil',
                ext / 'mapping/30.0.0.compat.cil',
                product / 'product_sepolicy.cil', product / 'mapping/30.0.0.cil']
    inputs = required[:2] + [p for p in optional if p.is_file()] + required[2:]
    aliases = []
    for directory, suffix in [(system, '.cil'), (system, '.compat.cil'),
                              (ext, '.compat.cil')]:
        source = directory / ('mapping/30.0' + suffix)
        target = directory / ('mapping/30.0.0' + suffix)
        expected = re.sub(r'\b([A-Za-z0-9_]+)_30_0\b', r'\1_30_0_0',
                          source.read_text())
        matches = target.read_text() == expected
        aliases.append({'path': str(target), 'matches_version_renamed_source': matches})
        if not matches:
            raise SystemExit(f'Unexpected compatibility mapping contents: {target}')
    results = {}
    for name, extra in [('android_init', ['-N']), ('strict_audit', [])]:
        output = args.out / (name + '.bin')
        command = [str(args.secilc), '-m', '-M', 'true', '-G', *extra, '-c', '30',
                   *map(str, inputs), '-o', str(output), '-f', '/dev/null']
        result = subprocess.run(command, text=True, capture_output=True)
        (args.out / (name + '.stderr')).write_text(result.stderr)
        (args.out / (name + '.stdout')).write_text(result.stdout)
        results[name] = {'exit_code': result.returncode,
                         'neverallow_checks_enabled': not extra,
                         'output_sha256': digest(output) if result.returncode == 0 else None,
                         'stderr_file': str(args.out / (name + '.stderr'))}
    report = {'scope': 'Offline candidate split policy plus stock vendor; no boot test.',
              'boot_tested': False, 'changes_enforcement': False,
              'inputs': [{'path': str(p), 'sha256': digest(p)} for p in inputs],
              'mapping_checks': aliases, 'compilation': results,
              'strict_audit_passed': results['strict_audit']['exit_code'] == 0}
    (args.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'report': str(args.out / 'report.json'), 'compilation': results}, indent=2))
    raise SystemExit(results['android_init']['exit_code'])


if __name__ == '__main__':
    main()
