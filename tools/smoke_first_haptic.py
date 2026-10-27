"""Execute the original and patched ARM64 knock path with controlled inputs.

No game or ROM is executed. Unicorn runs only the guarded instruction slice;
the knock getter and SDL rumble calls are replaced with deterministic hooks.
"""
from pathlib import Path
import json
import struct
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm64_const import *
from native_first_haptic import GUARD_VA, BRANCH_VA, GUARD, OLD, NOP, file_offset, verify, patch

END = GUARD_VA + len(GUARD)
KNOCK = 0x1000ba060
RUMBLE = 0x100114c88

def execute(code, previous, sequence, *, enabled=True, menu=False, racing=True, kind=1, controllers=1):
    cpu = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    cpu.mem_map(0x100000000, 0x200000)
    cpu.mem_write(GUARD_VA, code)
    app, vector, stack = 0x2000000, 0x2001000, 0x3008000
    cpu.mem_map(app,0x20000)
    cpu.mem_map(0x3000000,0x10000)
    cpu.mem_write(app+0x1f4,struct.pack('<I',previous))
    cpu.mem_write(app+0xd8,struct.pack('<QQ',vector,vector+controllers*8))
    for i in range(controllers): cpu.mem_write(vector+i*8,struct.pack('<Q',0x12340000+i))
    for reg,value in [(UC_ARM64_REG_SP,stack),(UC_ARM64_REG_X19,app),
                      (UC_ARM64_REG_X22,int(enabled)),(UC_ARM64_REG_X24,int(menu)),
                      (UC_ARM64_REG_X26,int(racing))]:
        cpu.reg_write(reg,value)
    calls = []
    def hook(cpu,address,size,user):
        if address == KNOCK:
            cpu.mem_write(cpu.reg_read(UC_ARM64_REG_X0),struct.pack('<f',0.75))
            cpu.mem_write(cpu.reg_read(UC_ARM64_REG_X1),struct.pack('<I',kind))
            cpu.reg_write(UC_ARM64_REG_X0,sequence)
            cpu.reg_write(UC_ARM64_REG_PC,cpu.reg_read(UC_ARM64_REG_LR))
        elif address == RUMBLE:
            calls.append(tuple(cpu.reg_read(reg) for reg in
                [UC_ARM64_REG_X0,UC_ARM64_REG_X1,UC_ARM64_REG_X2,UC_ARM64_REG_X3]))
            cpu.reg_write(UC_ARM64_REG_X0,0)
            cpu.reg_write(UC_ARM64_REG_PC,cpu.reg_read(UC_ARM64_REG_LR))
    cpu.hook_add(UC_HOOK_CODE,hook)
    cpu.emu_start(GUARD_VA,END,count=1000)
    assert cpu.reg_read(UC_ARM64_REG_PC) == END
    seen = struct.unpack('<I',cpu.mem_read(app+0x1f4,4))[0]
    return calls,seen

converted = Path('build/SegaRally.app/port0r').read_bytes()
prepared = Path('extracted/Port0r Rally.app/Contents/MacOS/port0r').read_bytes()
for binary in [prepared,converted]: verify(binary,patched=True)
position = file_offset(converted,GUARD_VA,len(GUARD))
fixed = converted[position:position+len(GUARD)]
assert execute(GUARD,0,1) == ([],1)  # reproduce the upstream first-event discard
assert execute(fixed,0,1) == ([(0x12340000,49151,49151,80)],1)
for code in [GUARD,fixed]:
    assert execute(code,0,0) == ([],0)
    assert execute(code,1,1) == ([],1)
    assert execute(code,1,2,kind=2) == ([(0x12340000,49151,49151,110)],2)
    for flags in [{'enabled':False},{'menu':True},{'racing':False}]:
        assert execute(code,0,1,**flags) == ([],1)
    assert execute(code,1,2,controllers=0) == ([],2)
assert len(execute(fixed,0,1,controllers=2)[0]) == 2
assert execute(fixed,0,1,controllers=2)[0] == [
    (0x12340000,49151,49151,80),(0x12340001,49151,49151,80)]
original = bytearray(prepared)
branch = file_offset(original,BRANCH_VA,4)
original[branch:branch+4] = OLD
assert patch(original) == prepared
original[branch+8] ^= 1
try:
    patch(original)
except ValueError:
    pass
else:
    raise AssertionError('Changed native code must be rejected')
Path('build/first-haptic-validation.json').write_text(json.dumps({
    'branch_va':hex(BRANCH_VA),'old_instruction':'cbz w8, 0x1000115f0',
    'new_instruction':'nop','upstream_first_knock_discard_reproduced':True,
    'patched_first_knock_one_request_per_controller':True,
    'duplicate_zero_menu_disabled_inactive_guards_preserved':True,
    'device_verified':False},indent=2))
print('PASS: actual original ARM64 code drops first knock; patched code emits first once, preserves later events/strengths/durations, zero/duplicate events and menu/disabled/inactive gates')
