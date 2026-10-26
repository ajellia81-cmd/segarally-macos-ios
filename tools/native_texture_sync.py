"""Enable the original renderer's existing texture-update completion fences.

Applied after native_guide.patch to the pinned official executable. Only two
configuration defaults change from 0 to 1: m2.regionsWaitIdle and
m2.sheetWaitIdle. The original Vulkan wait calls and their upload-only guards
remain unchanged. A saved explicit setting still overrides these defaults.
This is a diagnostic/compatibility build, not proof of the flicker cause.
"""
import hashlib
import struct

INPUT_SHA256 = '36c7a92c77a10243b70dc1728b1e43334795662ef55cc2a00c2268b89b1104a2'
SITES = ((0x5fa00, 'm2.regionsWaitIdle', 0x5f9f8),
         (0xa0d78, 'm2.sheetWaitIdle', 0xa0d70))


def patch(data):
    if hashlib.sha256(data).hexdigest() != INPUT_SHA256:
        raise ValueError('Unsupported input for native texture synchronization patch')
    result = bytearray(data)
    for offset, key, start in SITES:
        if struct.unpack_from('<I', data, offset)[0] != 0x52800001:
            raise ValueError(f'Unexpected original default for {key}')
        if struct.unpack_from('<I', data, offset + 8)[0] != 0x34000060:
            raise ValueError(f'Unexpected original wait guard for {key}')
        struct.pack_into('<I', result, offset, 0x52800021)  # mov w1, #1
    return bytes(result)
