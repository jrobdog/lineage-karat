"""Regression tests against captured metadata and intentionally damaged images.

Large fixtures use sparse temporary files, not additional copies of the firmware.
"""
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))
from extract_super import read_metadata
from check_candidate import inspect

METADATA = json.loads((PROJECT / 'reports/stock-super.json').read_text())
SOURCE = Path(METADATA['source'])


@unittest.skipUnless(SOURCE.is_file(), 'Captured stock super image required')
class MetadataValidation(unittest.TestCase):
    def fixture(self, change):
        length = 12288 + METADATA['metadata_max_size'] * METADATA['metadata_slots'] * 2
        with SOURCE.open('rb') as source:
            prefix = bytearray(source.read(length))
        change(prefix)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'super.img'
            with path.open('wb') as fixture:
                fixture.write(prefix)
                fixture.truncate(METADATA['image_size'])
            return read_metadata(path)

    def test_stock_geometry(self):
        parsed = self.fixture(lambda data: None)
        self.assertEqual({p['name']: p['size'] for p in parsed['partitions']},
                         {p['name']: p['size'] for p in METADATA['partitions']})

    def test_bad_geometry_checksum(self):
        def change(data):
            data[4096 + 20] ^= 1
        with self.assertRaisesRegex(ValueError, 'geometry checksum'):
            self.fixture(change)

    def test_bad_partition_table_checksum(self):
        def change(data):
            data[12288 + 128 + 8] ^= 1
        with self.assertRaisesRegex(ValueError, 'table checksum'):
            self.fixture(change)

    def test_extent_outside_device_even_with_valid_checksums(self):
        def change(data):
            offset = 12288
            header = bytearray(data[offset:offset + 128])
            table_size = struct.unpack_from('<I', header, 44)[0]
            tables = bytearray(data[offset + 128:offset + 128 + table_size])
            extent_table = struct.unpack_from('<I', header, 92)[0]
            struct.pack_into('<Q', tables, extent_table + 12, METADATA['image_size'] // 512 + 1)
            header[48:80] = hashlib.sha256(tables).digest()
            header[12:44] = bytes(32)
            header[12:44] = hashlib.sha256(header).digest()
            updated = header + tables
            backup = offset + METADATA['metadata_max_size'] * METADATA['metadata_slots']
            data[offset:offset + len(updated)] = updated
            data[backup:backup + len(updated)] = updated
        with self.assertRaisesRegex(ValueError, 'Extent outside'):
            self.fixture(change)


class CandidateValidation(unittest.TestCase):
    def test_sparse_container_cannot_pass_as_raw_size(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'system.img'
            path.write_bytes(bytes.fromhex('3aff26ed') + bytes(2044))
            with self.assertRaisesRegex(ValueError, 'sparse input'):
                inspect(path, METADATA)

    def test_non_filesystem_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'system.img'
            path.write_bytes(bytes(4096))
            with self.assertRaisesRegex(ValueError, 'not a raw ext4'):
                inspect(path, METADATA)

    @unittest.skipUnless((PROJECT / 'stock/images/system.img').is_file(), 'Stock system required')
    def test_truncated_filesystem_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'system.img'
            with (PROJECT / 'stock/images/system.img').open('rb') as source:
                path.write_bytes(source.read(4096))
            with self.assertRaisesRegex(ValueError, 'Filesystem extends beyond'):
                inspect(path, METADATA)

    @unittest.skipUnless((PROJECT / 'stock/images/system.img').is_file(), 'Stock system required')
    def test_image_exceeding_super_budget_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'system.img'
            with (PROJECT / 'stock/images/system.img').open('rb') as source:
                header = source.read(4096)
            with path.open('wb') as image:
                image.write(header)
                image.truncate(1470902272 + 4096)
            with self.assertRaisesRegex(ValueError, 'exceeds .*system budget'):
                inspect(path, METADATA)


if __name__ == '__main__':
    unittest.main()
