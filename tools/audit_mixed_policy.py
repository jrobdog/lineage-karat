#!/usr/bin/env python3
"""Audit Lineage platform policy against stock karat vendor policy, offline.

Writes only to a separate audit directory. Version-renamed mappings are an
analysis experiment, never installed into the build. Neverallow checks stay on.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system', type=Path, required=True)
    parser.add_argument('--stock-policy', type=Path, required=True)
    parser.add_argument('--secilc', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    parts = [('system', args.system / 'etc/selinux', 'plat_sepolicy.cil'),
             ('system_ext', args.system / 'system_ext/etc/selinux', 'system_ext_sepolicy.cil'),
             ('product', args.system / 'product/etc/selinux', 'product_sepolicy.cil')]
    inputs, aliases, missing = [], [], []
    for name, directory, policy in parts:
        if not (directory / policy).is_file():
            continue
        inputs.append(directory / policy)
        runtime_mapping = directory / 'mapping/30.0.0.cil'
        if not runtime_mapping.exists():
            missing.append(str(runtime_mapping))
        for suffix in ['.cil', '.compat.cil']:
            source = directory / ('mapping/30.0' + suffix)
            if source.exists():
                target = args.out / (name + '-30.0.0' + suffix)
                # Keep target-policy types unchanged; rename only API attributes.
                target.write_text(re.sub(r'\b([A-Za-z0-9_]+)_30_0\b',
                                         r'\1_30_0_0', source.read_text()))
                inputs.append(target)
                aliases.append({'source': str(source), 'audit_mapping': str(target)})
    inputs += [args.stock_policy / 'vendor/plat_pub_versioned.cil',
               args.stock_policy / 'vendor/vendor_sepolicy.cil']
    command = [str(args.secilc), '-m', '-M', 'true', '-G', '-c', '30',
               *map(str, inputs), '-o', str(args.out / 'mixed-policy.bin'), '-f', '/dev/null']
    result = subprocess.run(command, capture_output=True, text=True)
    report = {'scope': 'Offline audit using version-renamed AOSP compatibility mappings only.',
              'installed_into_build': False, 'neverallow_checks_disabled': False,
              'missing_runtime_mappings': missing, 'audit_mapping_inputs': aliases,
              'compiler_exit_code': result.returncode, 'stderr': result.stderr,
              'mixed_policy_compiles_with_aliases': result.returncode == 0,
              'boot_tested': False}
    (args.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'compiler_exit_code': result.returncode,
                      'missing_runtime_mappings': missing,
                      'stderr_lines': len(result.stderr.splitlines()),
                      'report': str(args.out / 'report.json')}, indent=2))


if __name__ == '__main__':
    main()
