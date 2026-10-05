import argparse
import pathlib
import struct
import sys
import zipfile

PAGE_SIZE = 16384
MACHINES = {62: "x86_64", 183: "arm64-v8a"}
PT_LOAD = 1
PT_GNU_RELRO = 0x6474E552


def inspect_elf(data, label):
    if len(data) < 16 or data[:4] != b"\x7fELF":
        raise ValueError(f"{label}: not an ELF file")
    if data[4] == 1:
        return None
    if data[4] != 2 or data[5] not in (1, 2):
        raise ValueError(f"{label}: unsupported ELF encoding")
    endian = "<" if data[5] == 1 else ">"
    header_format = struct.Struct(endian + "16sHHIQQQIHHHHHH")
    if len(data) < header_format.size:
        raise ValueError(f"{label}: truncated ELF header")
    header = header_format.unpack_from(data)
    machine = header[2]
    if machine not in MACHINES:
        return None
    program_offset, entry_size, entry_count = header[5], header[9], header[10]
    program_format = struct.Struct(endian + "IIQQQQQQ")
    if entry_count == 0xFFFF:
        raise ValueError(f"{label}: extended program-header count unsupported")
    if not entry_count or entry_size < program_format.size:
        raise ValueError(f"{label}: invalid program-header table")
    if program_offset + entry_size * entry_count > len(data):
        raise ValueError(f"{label}: truncated program-header table")
    segments = [
        program_format.unpack_from(data, program_offset + entry_size * entry_index)
        for entry_index in range(entry_count)
    ]
    loads = [segment for segment in segments if segment[0] == PT_LOAD]
    if not loads:
        raise ValueError(f"{label}: no LOAD segments")
    load_ok = all(segment[7] >= PAGE_SIZE for segment in loads)
    relro_segments = [segment for segment in segments if segment[0] == PT_GNU_RELRO]
    relro_ok = all(
        (segment[3] + segment[6]) % PAGE_SIZE == 0 for segment in relro_segments
    )
    print(f"{label} ({MACHINES[machine]})")
    print(f"  LOAD alignment: {'PASS' if load_ok else 'FAIL'}")
    for segment in relro_segments:
        address, memory_size = segment[3], segment[6]
        end = address + memory_size
        print(
            f"  GNU_RELRO: vaddr={address:#x} memsz={memory_size:#x} "
            f"end={end:#x} remainder={end % PAGE_SIZE:#x}"
        )
    print(f"  RELRO end modulo 16 KB: {'PASS' if relro_ok else 'FAIL'}")
    return load_ok and relro_ok


def native_files(source):
    if source.is_dir():
        for library in sorted(source.rglob("*.so")):
            yield library.relative_to(source).as_posix(), library.read_bytes()
    elif zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as archive:
            for member in sorted(archive.namelist()):
                if member.endswith(".so"):
                    yield member, archive.read(member)
    else:
        yield source.name, source.read_bytes()


def main():
    parser = argparse.ArgumentParser(
        description="Check 64-bit ELF LOAD and GNU_RELRO layout, not runtime compatibility."
    )
    parser.add_argument("source", type=pathlib.Path, help="APK, AAR, .so, or directory")
    args = parser.parse_args()
    checked = 0
    failures = 0
    try:
        for label, data in native_files(args.source):
            result = inspect_elf(data, label)
            if result is not None:
                checked += 1
                failures += not result
        if not checked:
            raise ValueError("No ARM64 or x86_64 ELF libraries found")
    except (OSError, ValueError, zipfile.BadZipFile, struct.error) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(f"Checked {checked} libraries; {failures} failed static layout checks.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
