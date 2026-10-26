"""Exercise the actual generated family hook with phone and Mac device answers.

This tests capability forwarding, not real-device rendering or flicker.
"""
from pathlib import Path
import re
import subprocess

source = Path('compatibility/shim/overrides/AppKit_RuntimeHooks.m').read_text()
match = re.search(r'static IMP gSupportsFamily;\nstatic BOOL ShimSupportsFamily\([^\n]+\) \{.*?\n\}', source, re.S)
assert match, 'GPU capability hook missing'
hook = match.group()
assert 'return YES' not in hook
test = Path('build/gpu_capabilities_smoke.m')
test.write_text('#import <Foundation/Foundation.h>\n#import <Metal/Metal.h>\n#import <objc/runtime.h>\n#include <assert.h>\n' + hook + r'''
static int queries;
static id lastDevice;
static SEL lastSelector;
static MTLGPUFamily lastFamily;
static BOOL NativeDevice(id device, SEL selector, MTLGPUFamily family) {
    queries++; lastDevice = device; lastSelector = selector; lastFamily = family;
    if (family == MTLGPUFamilyMac2) return [device isEqual:@"Mac"];
    return family == MTLGPUFamilyApple9;
}
int main(void) { @autoreleasepool {
    gSupportsFamily = (IMP)NativeDevice;
    SEL selector = @selector(supportsFamily:);
    assert(!ShimSupportsFamily(@"iPhone", selector, MTLGPUFamilyMac2));
    assert(queries == 1 && lastDevice == @"iPhone" && lastSelector == selector && lastFamily == MTLGPUFamilyMac2);
    assert(ShimSupportsFamily(@"iPhone", selector, MTLGPUFamilyApple9));
    assert(!ShimSupportsFamily(@"iPhone", selector, MTLGPUFamilyApple8));
    assert(ShimSupportsFamily(@"Mac", selector, MTLGPUFamilyMac2));
    assert(queries == 4); // every query reaches the native implementation
    puts("PASS: native GPU family answers preserved; unsupported Mac2 no longer forced true; supported families unchanged");
} return 0; }
''')
subprocess.run(['xcrun','--sdk','macosx','clang','-fobjc-arc','-fsanitize=address',
                '-framework','Foundation','-framework','Metal',str(test),
                '-o','build/gpu_capabilities_smoke'],check=True)
subprocess.run(['build/gpu_capabilities_smoke'],check=True)
Path('build/gpu-capabilities-validation.txt').write_text(
    'GPU family spoof disabled: queries forward unchanged to the actual device.\n'
    'Original MoltenVK, game renderer, emulator, MSAA, speed and frame-rate preferences unchanged.\n'
    'Actual iPhone flicker cause and outcome remain unverified.\n')
