#!/usr/bin/env python3
"""Compile the extracted stock split policy as an offline reference fixture.

Run with the freshly built host secilc in the build container. Neverallow checks
remain enabled. This validates the stock inputs, not a mixed Lineage/vendor OS.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--secilc', type=Path, required=True)
    parser.add_argument('--policy-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    root = args.policy_root
    version = (root / 'vendor/plat_sepolicy_vers.txt').read_text().strip()
    if version != '30.0.0':
        raise ValueError('Expected captured karat policy version 30.0.0')
    inputs = [root / p for p in [
        'system/plat_sepolicy.cil', 'system/mapping/30.0.0.cil',
        'system_ext/system_ext_sepolicy.cil', 'system_ext/mapping/30.0.0.cil',
        'vendor/plat_pub_versioned.cil', 'vendor/vendor_sepolicy.cil']]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    command = [str(args.secilc), '-m', '-M', 'true', '-G', '-c', '30',
               *map(str, inputs), '-o', str(args.output), '-f', '/dev/null']
    result = subprocess.run(command, capture_output=True, text=True)
    report = {'scope': 'Stock split policy only; no Lineage platform policy is substituted.',
              'vendor_policy_version': version, 'neverallow_checks_disabled': False,
              'compiler_sha256': sha256(args.secilc),
              'inputs': {str(p.relative_to(root)): sha256(p) for p in inputs},
              'exit_code': result.returncode, 'stderr': result.stderr,
              'output_sha256': sha256(args.output) if result.returncode == 0 else None}
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'exit_code': result.returncode, 'output_sha256': report['output_sha256']}))
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
