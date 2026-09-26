#!/usr/bin/env python3
"""Extract a raw, single-device Android super image without modifying it.

Format reference: AOSP system/core/fs_mgr/liblp/include/liblp/metadata_format.h.
Geometry, metadata header and table checksums are verified before extraction.
Sparse Android images and metadata spanning multiple devices are rejected.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

SECTOR = 512


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_at(stream, offset, size):
    stream.seek(offset)
    data = stream.read(size)
    require(len(data) == size, f"Truncated input at offset {offset}")
    return data


def checked_hash(data, offset, expected, label):
    data = bytearray(data)
    data[offset:offset + 32] = bytes(32)
    require(hashlib.sha256(data).digest() == expected, f"Invalid {label} checksum")


def name_of(raw):
    name = raw.split(b"\0", 1)[0].decode("ascii")
    require(re.fullmatch(r"[A-Za-z0-9_]+", name) is not None, "Invalid partition/group name")
    return name


def read_metadata(path):
    path = Path(path)
    image_size = path.stat().st_size
    with path.open("rb") as stream:
        require(read_at(stream, 0, 4) != bytes.fromhex("3aff26ed"), "Use an unsparsed raw image")
        geometry = read_at(stream, 4096, 52)
        magic, size, digest, maximum, slots, block_size = struct.unpack("<II32sIII", geometry)
        require(magic == 0x616C4467 and size == 52, "Unsupported super geometry")
        checked_hash(geometry, 8, digest, "geometry")
        require(read_at(stream, 8192, 52) == geometry, "Geometry copies differ")
        require(0 < maximum <= 4 * 1024 * 1024 and maximum % SECTOR == 0, "Invalid metadata size")
        require(1 <= slots <= 3 and block_size >= SECTOR and block_size % SECTOR == 0, "Invalid geometry")
        offset = 12288
        prefix = read_at(stream, offset, 128)
        magic, major, minor, header_size = struct.unpack_from("<IHHI", prefix)
        require(magic == 0x414C5030 and major == 10 and minor <= 2, "Unsupported metadata version")
        require(header_size in (128, 256) and header_size <= maximum, "Invalid metadata header size")
        header = read_at(stream, offset, header_size)
        checked_hash(header, 12, header[12:44], "metadata header")
        tables_size = struct.unpack_from("<I", header, 44)[0]
        require(tables_size <= maximum - header_size, "Tables exceed metadata allocation")
        tables = read_at(stream, offset + header_size, tables_size)
        require(hashlib.sha256(tables).digest() == header[48:80], "Invalid metadata table checksum")
        primary = header + tables
        require(read_at(stream, offset + maximum * slots, len(primary)) == primary, "Primary/backup slot 0 metadata differ")

    def table(index, fmt):
        start, count, entry_size = struct.unpack_from("<III", header, 80 + index * 12)
        require(entry_size == struct.calcsize(fmt), "Unsupported metadata entry size")
        require(start + count * entry_size <= len(tables), "Metadata table out of bounds")
        return [struct.unpack_from(fmt, tables, start + i * entry_size) for i in range(count)]

    partitions = table(0, "<36sIIII")
    extents = table(1, "<QIQI")
    groups = [{"name": name_of(n), "flags": flags, "maximum_size": size} for n, flags, size in table(2, "<36sIQ")]
    devices = table(3, "<QIIQ36sI")
    require(len(devices) == 1, "Only single-device super images are supported")
    first_sector, alignment, alignment_offset, device_size, device_name, flags = devices[0]
    require(device_size == image_size, "Recorded block-device size differs from image size")
    require(first_sector * SECTOR >= 12288 + maximum * slots * 2, "Data overlaps metadata")
    parsed = []
    names = set()
    physical_ranges = []
    for raw_name, attributes, start, count, group in partitions:
        name = name_of(raw_name)
        require(name not in names, "Duplicate partition name")
        names.add(name)
        require(count > 0 and start + count <= len(extents) and group < len(groups), "Invalid partition extents/group")
        entries = []
        for sectors, kind, data, source in extents[start:start + count]:
            require(sectors > 0 and sectors * SECTOR <= image_size, "Invalid extent length")
            require(kind in (0, 1) and source == 0, "Unsupported extent target")
            if kind == 0:
                require(data >= first_sector and (data + sectors) * SECTOR <= image_size, "Extent outside data region")
                physical_ranges.append((data, data + sectors))
            else:
                require(data == 0, "Invalid zero extent")
            entries.append({"sectors": sectors, "kind": kind, "physical_sector": data})
        parsed.append({"name": name, "attributes": attributes, "group": groups[group]["name"], "size": sum(e["sectors"] * SECTOR for e in entries), "extents": entries})
    physical_ranges.sort()
    require(all(a[1] <= b[0] for a, b in zip(physical_ranges, physical_ranges[1:])), "Overlapping physical extents")
    for group in groups:
        used = sum(p["size"] for p in parsed if p["group"] == group["name"])
        require(group["maximum_size"] == 0 or used <= group["maximum_size"], "Group allocation exceeds its maximum")
    return {"source": str(path.resolve()), "image_size": image_size, "metadata_version": [major, minor], "metadata_slots": slots, "metadata_max_size": maximum, "logical_block_size": block_size, "block_device": name_of(device_name), "alignment": alignment, "alignment_offset": alignment_offset, "groups": groups, "partitions": parsed, "checksums_verified": True}


def extract(path, output, metadata):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    require(not any((output / (p["name"] + ".img")).exists() for p in metadata["partitions"]), "Refusing to overwrite extracted images")
    with Path(path).open("rb") as source:
        for partition in metadata["partitions"]:
            destination = output / (partition["name"] + ".img")
            temporary = destination.with_suffix(".partial")
            digest = hashlib.sha256()
            with temporary.open("xb") as target:
                for extent in partition["extents"]:
                    remaining = extent["sectors"] * SECTOR
                    source.seek(extent["physical_sector"] * SECTOR)
                    while remaining:
                        length = min(1024 * 1024, remaining)
                        data = source.read(length) if extent["kind"] == 0 else bytes(length)
                        require(len(data) == length, "Incomplete extent read")
                        target.write(data)
                        digest.update(data)
                        remaining -= length
            require(temporary.stat().st_size == partition["size"], "Extracted size mismatch")
            temporary.replace(destination)
            partition["sha256"] = digest.hexdigest()
            partition["extracted_path"] = str(destination.resolve())
            print(f"Extracted {partition['name']}: {partition['size']:,} bytes", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    metadata = read_metadata(args.image)
    if args.out:
        extract(args.image, args.out, metadata)
    args.manifest.write_text(json.dumps(metadata, indent=2) + "\n")
    print("Verified super metadata and partition bounds", flush=True)


if __name__ == "__main__":
    main()
