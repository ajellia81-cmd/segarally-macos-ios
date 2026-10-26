"""Execute the renderer's original fence guards with controlled Vulkan calls.

Uses the actual ARM64 default/branch/device-load instructions. Relocates only
external addresses; no Vulkan device or game data is created.
"""
from pathlib import Path
import json
import struct
import subprocess
import tarfile
from native_texture_sync import patch, SITES
from native_guide import patch as guide

with tarfile.open('port0r.tar.gz') as archive:
    member = next(m for m in archive.getmembers() if m.name.endswith('Contents/MacOS/port0r'))
    original = archive.extractfile(member).read()
baseline = guide(original)
modified = patch(baseline)
prepared = Path('extracted/Port0r Rally.app/Contents/MacOS/port0r').read_bytes()
assert modified == prepared
allowed = {offset for offset, _, _ in SITES}
assert all(i // 4 * 4 in allowed for i,(a,b) in enumerate(zip(baseline,modified)) if a != b)

# Prove that each existing wait call really is vkDeviceWaitIdle, by following
# Mach-O's stub/indirect symbol table, instead of trusting a guessed address.
pos = 32
for _ in range(struct.unpack_from('<I', original, 16)[0]):
    command, size = struct.unpack_from('<II', original, pos)
    if command == 2: symbols, count, strings, string_size = struct.unpack_from('<IIII',original,pos+8)
    if command == 0xb: indirect, indirect_count = struct.unpack_from('<II',original,pos+56)
    if command == 0x19:
        for i in range(struct.unpack_from('<I',original,pos+64)[0]):
            section = pos+72+i*80
            if original[section:section+16].split(b'\0')[0] == b'__stubs':
                stub_base = struct.unpack_from('<Q',original,section+32)[0]
                first_stub, stride = struct.unpack_from('<II',original,section+68)
    pos += size

assembly = ['.text','.p2align 2']
names = []
for i,(offset,key,start) in enumerate(SITES):
    call_offset = offset+16
    word = struct.unpack_from('<I',original,call_offset)[0]
    assert word & 0xfc000000 == 0x94000000
    relative = word & 0x3ffffff
    if relative & (1<<25): relative -= 1<<26
    target = 0x100000000+call_offset+relative*4
    slot = first_stub+(target-stub_base)//stride
    symbol = struct.unpack_from('<I',original,indirect+4*slot)[0]
    index = struct.unpack_from('<I',original,symbols+16*symbol)[0]
    actual_name = original[strings+index:original.index(b'\0',strings+index)].decode()
    assert actual_name == '_vkDeviceWaitIdle'
    for label,data in [('Original',baseline),('Synced',modified)]:
        name = f'{label}{i}'
        names.append(name)
        # Keep both native device-register choices (x20 vs x25) intact.
        assembly += [f'.globl _{name}',f'_{name}:',
            'stp x20,x25,[sp,#-32]!', 'stp x29,x30,[sp,#16]',
            'mov x20,x0','mov x25,x0',f'adrp x0, _Key{i}@PAGE',f'add x0,x0,_Key{i}@PAGEOFF',
            f'.long 0x{struct.unpack_from("<I",data,offset)[0]:08x}',
            'bl _MockConfig', f'.long 0x{struct.unpack_from("<I",data,offset+8)[0]:08x}',
            f'.long 0x{struct.unpack_from("<I",data,offset+12)[0]:08x}',
            'bl _MockWait', 'ldp x29,x30,[sp,#16]', 'ldp x20,x25,[sp],#32', 'ret']
Path('build/texture_sync_guard.s').write_text('\n'.join(assembly)+'\n')
Path('build/texture_sync_smoke.c').write_text(r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>
const char Key0[] = "m2.regionsWaitIdle";
const char Key1[] = "m2.sheetWaitIdle";
static int override=-1, waits, queries;
static const char *expected;
int MockConfig(const char *key, int fallback) {
    assert(!strcmp(key,expected)); queries++; return override<0 ? fallback : override;
}
int MockWait(void *device) { assert(device==(void*)(uintptr_t)0x1234); waits++; return 0; }
extern void Original0(void *), Original1(void *), Synced0(void *), Synced1(void *);
int main(void) {
    uintptr_t renderer[0xd68/8] = {0}; renderer[0xd60/8] = 0x1234;
    void (*original[])(void*)={Original0,Original1};
    void (*synced[])(void*)={Synced0,Synced1};
    const char *keys[]={Key0,Key1};
    for(int i=0;i<2;i++) {
        expected=keys[i]; override=-1; waits=queries=0;
        original[i](renderer); assert(queries==1 && waits==0);
        synced[i](renderer); assert(queries==2 && waits==1);
        override=0; synced[i](renderer); assert(waits==1); // explicit saved override retained
        override=1; original[i](renderer); assert(waits==2); // original path already supports the fence
    }
    puts("PASS: actual ARM64 texture guards enable the existing Vulkan completion fence by default, preserve explicit overrides and leave unrelated rendering untouched");
    return 0;
}
''')
subprocess.run(['xcrun','--sdk','macosx','clang','-arch','arm64','-fsanitize=address',
                'build/texture_sync_smoke.c','build/texture_sync_guard.s','-o','build/texture_sync_smoke'],check=True)
subprocess.run(['build/texture_sync_smoke'],check=True)
Path('build/texture-sync-validation.json').write_text(json.dumps({
    'defaults':{key:1 for _,key,_ in SITES},'wait_function':'vkDeviceWaitIdle',
    'modified_instructions':2,'emulator_and_shaders':'unchanged',
    'flicker_device_verified':False,'performance_device_verified':False},indent=2))
