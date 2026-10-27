"""Remove only the pinned Port0r branch that discards the first knock event."""
import struct
GUARD_VA = 0x100011528
BRANCH_VA = 0x10001155c
GUARD = bytes.fromhex('ff6300b9ff4b00b9e0830191e1230191caa2029468f641b91f00086b00060054f50300aaf7f30129f92f00b9f9031baafc031aaaa8040034c802005268040037580400358803005208040037e84b40b9090a8052ca0d80521f0900715601891ae06340bd01102e1e0158211e08e09f52e8efa8720201271e2108221ea899995288a9a7720201271e0020221e0880995288a9a8720001271e004c211e7aee4da95f031beb200100541700381e408740f8e10317aae20317aae30316aaa90d04945f031beb41ffff5475f601b9fa031caafb0319aaf92f40b9f7f34129')
OLD = bytes.fromhex('a8040034')  # cbz w8, 0x1000115f0: previous event number == 0
NOP = bytes.fromhex('1f2003d5')

def file_offset(data, address, length):
    if len(data) < 32 or data[:4] != b'\xcf\xfa\xed\xfe':
        raise ValueError('Expected thin little-endian Mach-O 64')
    position = 32
    for _ in range(struct.unpack_from('<I',data,16)[0]):
        if position + 8 > len(data): raise ValueError('Truncated command')
        command,size = struct.unpack_from('<II',data,position)
        if size < 8 or position + size > len(data): raise ValueError('Invalid command')
        if command == 0x19:
            if size < 72: raise ValueError('Invalid segment')
            virtual,vsize,offset,fsize = struct.unpack_from('<QQQQ',data,position+24)
            if virtual <= address and address + length <= virtual + fsize:
                result = offset + address - virtual
                if result + length > len(data): raise ValueError('Truncated segment')
                return result
        position += size
    raise ValueError('Address not in a file-backed segment')

def expected_guard(patched=False):
    expected = bytearray(GUARD)
    if patched:
        delta = BRANCH_VA - GUARD_VA
        expected[delta:delta+4] = NOP
    return bytes(expected)

def verify(data, patched=False):
    start = file_offset(data, GUARD_VA, len(GUARD))
    if data[start:start+len(GUARD)] != expected_guard(patched):
        raise ValueError('Pinned first-knock code changed; review required')
    return start

def patch(data):
    verify(data)
    position = file_offset(data, BRANCH_VA, 4)
    if data[position:position+4] != OLD: raise ValueError('First-knock branch mismatch')
    result = bytearray(data)
    result[position:position+4] = NOP
    verify(result, patched=True)
    return bytes(result)
