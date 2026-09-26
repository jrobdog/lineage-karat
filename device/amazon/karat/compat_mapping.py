#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Translate the API-30 attribute suffix to karat's vendor version spelling.

No types, permissions, allow rules or enforcement settings are added or removed.
The source is the corresponding AOSP-generated compatibility mapping.
"""
import argparse
from pathlib import Path
import re


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    text = args.input.read_text()
    text = re.sub(r'\b([A-Za-z0-9_]+)_30_0\b', r'\1_30_0_0', text)
    args.output.write_text(text)


if __name__ == '__main__':
    main()
