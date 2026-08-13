#!/usr/bin/env python3
"""Print basic info of an Android boot image (for CI sanity checks)."""
import struct
import sys

def main():
    path = sys.argv[1]
    d = open(path, 'rb').read()
    assert d[:8] == b"ANDROID!", f"not an Android boot image: {path}"
    page = struct.unpack('<I', d[36:40])[0]
    hver = struct.unpack('<I', d[40:44])[0]
    ksz = struct.unpack('<I', d[8:12])[0]
    rsz = struct.unpack('<I', d[16:20])[0]
    dtb = struct.unpack('<I', d[1648:1652])[0]
    avb = d[-64:-60] == b'AVBf'
    assert hver == 2, f"boot image must be header v2, got v{hver}"
    print(f"boot: {len(d)} bytes, header v{hver}, page {page}, "
          f"kernel {ksz}, ramdisk {rsz}, dtb {dtb}, avb={avb}")

if __name__ == '__main__':
    main()
