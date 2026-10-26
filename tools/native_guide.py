"""Extend the original Port0r v0.1.0 Gamepad menu, without an overlay.

The engine already reads SDL Guide into bit 14 (Android-compatible key 110).
Its native menu table and string parser expose only twelve buttons. Append a
thirteenth entry, retain the first twelve indices, and extend the native menu
and parser. All edits happen before conversion/signing; no runtime code writes.
Only the pinned official executable is accepted.
"""
import hashlib
import struct

ORIGINAL_SHA256 = 'e19b0f75e25301f09f4156512acc1e2baa17053623ad9f4c822ebdd79c834c5e'
TABLE = 0x583410
LABELS = TABLE + 13 * 32
NEXT_MASK = 0xfff << 51
TARGET_MASK = (1 << 36) - 1
PARSER = bytes.fromhex(
    'f44fbea9fd7b01a9fd430091f30300aab42a00b094b646f9080080528916088b2'
    '90140f9ea0313aa2b1540384c1540387f010c6b810000548bffff35e003082a'
    '05000014080500111f35007183feff5400008012fd7b41a9f44fc2a8c0035fd6')
# ARM64 parser (same stack/unwind layout as the original):
# save x19/x20/fp/lr; load button-table GOT slot; for index 0..12 compare the
# input to table[index].settingName byte by byte; return index, otherwise -1.
# Uses only caller-saved x8..x12 and preserved x19/x20, with no external calls.


def u64(data, offset):
    return struct.unpack_from('<Q', data, offset)[0]


def chain(data, start):
    result = []
    offset = start
    while True:
        if offset in result:
            raise ValueError('Fixup chain cycle')
        result.append(offset)
        step = (u64(data, offset) >> 51) & 0xfff
        if not step:
            return result
        offset += step * 4


def patch(data):
    if hashlib.sha256(data).hexdigest() != ORIGINAL_SHA256:
        raise ValueError('Unsupported Port0r executable; native Guide patch refused')
    result = bytearray(data)
    # The final DATA_CONST page has file-backed, zero-filled alignment padding.
    # Do not move any segment, section, code, TLS or existing data addresses.
    if any(data[0x583408:0x584000]):
        raise ValueError('Expected unused DATA_CONST alignment padding')
    old_chain = chain(data, 0x5803a8)
    if old_chain[-1] != 0x5833f8:
        raise ValueError('Unexpected final DATA_CONST fixup')
    records = data[0x572d60:0x572ee0]
    result[TABLE:TABLE + len(records)] = records
    struct.pack_into('<QQiiii', result, TABLE + 12 * 32,
                     LABELS, LABELS + 6, 110, -1, -1, 0)
    result[LABELS:LABELS + 12] = b'GUIDE\0Guide\0'
    pointers = [TABLE + i * 32 + field for i in range(13) for field in (0, 8)]
    for offset, following in zip([old_chain[-1]] + pointers, pointers + [None]):
        value = u64(result, offset) & ~NEXT_MASK
        if following is not None:
            value |= ((following - offset) // 4) << 51
        struct.pack_into('<Q', result, offset, value)
    # Replace the self-import binding with a rebase to the extended table.
    # Preserve this GOT slot's link to the following original fixup.
    if u64(data, 0x570d68) != 0x80100000000001ad:
        raise ValueError('Unexpected native button-table import')
    struct.pack_into('<Q', result, 0x570d68, (u64(data, 0x570d68) & NEXT_MASK) | TABLE)
    # Native label-vector constructor: 12*32+8 -> 13*32+8.
    old = struct.unpack_from('<I', data, 0xe2d6c)[0]
    if (old >> 10) & 0xfff != 0x188:
        raise ValueError('Unexpected native menu label loop')
    struct.pack_into('<I', result, 0xe2d6c, (old & ~(0xfff << 10)) | (0x1a8 << 10))
    # Native settings callback keeps its button-table length in its own object.
    old = struct.unpack_from('<I', data, 0xe2f70)[0]
    if old != 0x52800188:  # mov w8, #12
        raise ValueError('Unexpected native menu callback length')
    struct.pack_into('<I', result, 0xe2f70, 0x528001a8)  # mov w8, #13
    result[0x1bf78:0x1bf78 + len(PARSER)] = PARSER
    if chain(result, 0x5803a8) != old_chain + pointers:
        raise ValueError('Extended fixup chain mismatch')
    if len(result) != len(data):
        raise ValueError('Native patch unexpectedly changed file size')
    return bytes(result)


def records(data):
    result = []
    for i in range(13):
        offset = TABLE + i * 32
        names = []
        for field in (0, 8):
            target = u64(data, offset + field) & TARGET_MASK
            names.append(data[target:data.index(b'\0', target)].decode())
        result.append((*names, *struct.unpack_from('<iiii', data, offset + 16)))
    return result
