#!/usr/bin/env python3
"""Swap the kernel in a boot v2 image, preserving ramdisk/dtb/AVB, mirroring the android_bootimg patcher."""
import struct, sys

def align(n, p=4096):
    return (n + p - 1) & ~(p - 1)

def swap(input_path, kernel_path, output_path):
    src = open(input_path, 'rb').read()
    kernel = open(kernel_path, 'rb').read()
    total_len = len(src)

    # --- parse boot header (v2) ---
    hdr = bytearray(src[:1660])
    page = struct.unpack("<I", hdr[36:40])[0]
    hver = struct.unpack("<I", hdr[40:44])[0]
    assert hdr[:8] == b"ANDROID!", "bad magic"
    assert hver == 2, f"only boot header v2 is supported, got v{hver}"
    assert page >= 4096
    kern_sz = struct.unpack("<I", hdr[8:12])[0]
    ram_sz  = struct.unpack("<I", hdr[16:20])[0]
    second_sz = struct.unpack("<I", hdr[24:28])[0]
    rdbo_sz  = struct.unpack("<I", hdr[1632:1636])[0]
    dtb_sz   = struct.unpack("<I", hdr[1648:1652])[0]
    hdr_size = struct.unpack("<I", hdr[1644:1648])[0]

    def block(off, size):
        return src[off:off+size] if size else b""
    kern_off = page
    off = kern_off + kern_sz
    ram_off = align(off); 
    off = ram_off + ram_sz
    second_off = align(off)
    off = second_off + second_sz
    rdbo_off = align(off)
    off = rdbo_off + rdbo_sz
    dtb_off = align(off)
    tail = align(dtb_off + dtb_sz)

    # --- AVB footer ---
    avb = None
    if src[-64:-60] == b"AVBf":
        ois = struct.unpack(">Q", src[-52:-44])[0]
        vbo = struct.unpack(">Q", src[-44:-36])[0]
        vbs = struct.unpack(">Q", src[-36:-28])[0]
        vbmeta = src[ois:ois+vbs]
        avb_tail = src[tail:ois]
        avb = (vbmeta, avb_tail)

    # --- rebuild ---
    out = bytearray()
    new_kern_sz = len(kernel)
    struct.pack_into("<I", hdr, 8, new_kern_sz)  # patch kernel_size
    out += hdr
    out += b"\0" * (align(len(out)) - len(out))   # header page
    out += kernel
    out += b"\0" * (align(len(out)) - len(out))
    out += block(ram_off, ram_sz)
    out += b"\0" * (align(len(out)) - len(out))
    out += block(second_off, second_sz)
    out += b"\0" * (align(len(out)) - len(out))
    out += block(rdbo_off, rdbo_sz)
    out += b"\0" * (align(len(out)) - len(out))
    out += block(dtb_off, dtb_sz)
    out += b"\0" * (align(len(out)) - len(out))
    total = len(out)

    if avb:
        vbmeta, avb_tail = avb
        out += avb_tail
        out += b"\0" * (align(len(out)) - len(out))
        vbo_new = len(out)
        out += vbmeta
        # footer
        footer = bytearray(src[-64:])
        struct.pack_into(">Q", footer, 12, total)   # original_image_size
        struct.pack_into(">Q", footer, 20, vbo_new) # vbmeta_offset
        end = total_len - 64
        if len(out) > end:
            sys.exit("no space left for avb structures")
        out += b"\0" * (end - len(out))
        out += footer
    else:
        if len(out) > total_len:
            sys.exit("image too large")
        out += b"\0" * (total_len - len(out))

    open(output_path, 'wb').write(bytes(out))
    print(f"wrote {output_path} ({len(out)} bytes, kernel {new_kern_sz})")

if __name__ == "__main__":
    swap(sys.argv[1], sys.argv[2], sys.argv[3])
