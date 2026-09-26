#!/usr/bin/env python3
"""Turn repo's pinned export into a portable standalone manifest.

Makes the GitHub fetch URL absolute; verifies every project has an exact SHA.
"""
import argparse
from pathlib import Path
import re
import xml.etree.ElementTree as ET


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    tree = ET.parse(args.input)
    root = tree.getroot()
    for project in root.findall('project'):
        if not re.fullmatch('[0-9a-f]{40}', project.get('revision', '')):
            raise ValueError(f'Unpinned project: {project.get("name")}')
    for remote in root.findall('remote'):
        if remote.get('name') == 'github':
            if remote.get('fetch') not in ('..', 'https://github.com'):
                raise ValueError('Unexpected GitHub remote URL')
            remote.set('fetch', 'https://github.com')
    ET.indent(tree, space='  ')
    tree.write(args.output, encoding='UTF-8', xml_declaration=True)
    print(f'Wrote {len(root.findall("project"))} revision-pinned projects to {args.output}')


if __name__ == '__main__':
    main()
