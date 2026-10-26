# Start-line background flicker investigation

Current disposition: the user found a matching symptom in an original Port0r
YouTube playthrough and requested an original-rendering stable IPA. The video
link has not been independently reviewed here, so this is user-reported baseline
evidence. The texture-sync experiment is removed from the default build. The
stable package preserves the pinned previously validated IPA's entire payload;
no flicker fix or newly compiled Xcode build is claimed for that package.

The user's October 26 recording shows background geometry flicker during the
start countdown. Changing the original frame-rate and speed settings does not
remove it; antialiasing was left at its default. This does not establish an
emulator defect or an iOS-port defect by itself.

## Confirmed compatibility problem

The pinned macOS-on-iOS converter's `ShimSupportsFamily` returns `YES` for
`MTLGPUFamilyMac2` unconditionally. This can give Vulkan a capability answer
different from the real iPhone device's answer. Port0r uses MoltenVK; MoltenVK's
device capability code reads `supportsFamily:MTLGPUFamilyMac2`.

The Port0r adaptation now forwards this query to the native implementation,
like every other GPU-family query. It logs actual Mac2/Apple9 answers at launch.
This fixes capability reporting. Whether it fixes this recording's flicker is
not yet verified on an iPhone.

For a controlled comparison, the original MoltenVK binary, game renderer,
emulator and all graphics preferences remain unchanged. No GPU serialization,
frame-rate limit, MSAA override or driver replacement is applied.

## Limits and comparison

Actions tests run the actual generated hook with controlled native answers;
they verify forwarding and preservation of supported families. They do not
render the user's copyrighted game scene or run on the user's iPhone.

Compare the prior IPA with this IPA using the same start-line scene and settings.
If flicker remains, collect the guest `Port0r-diagnostics/launch.log`, including
the native capability line and Vulkan render-pass/feature messages. An original
Mac baseline is still unavailable; no matching original Port0r issue was found
in the public issue search. Neither fact proves the emulator is correct.

Reference: https://github.com/KhronosGroup/MoltenVK/blob/v1.4.2/MoltenVK/MoltenVK/GPUObjects/MVKDevice.mm

## Device result and texture-update comparison

The user reports that truthful GPU-family reporting did not fix the flicker.
It remains a correctness fix, but it is not a demonstrated flicker fix. The
user identifies repeating building-window textures as the main affected area.

The pinned Port0r executable contains existing `m2.regionsWaitIdle` and
`m2.sheetWaitIdle` controls. Disassembly of both guarded paths, plus the Mach-O
indirect-symbol table, confirms that they call `vkDeviceWaitIdle` around texture
update work. Both original defaults are zero. The next comparison build changes
only those two default arguments to one; explicit config overrides still win.
The shaders, texture filtering, depth settings and emulator are unchanged.
Upload-time waits may cost performance; both the flicker and performance effects
need a device comparison. This is not unconditional synchronization of every
Metal command buffer.

## Emulator-side research

MAME 0.289's Model 2 renderer documents incomplete understanding of the original
Z-sort hardware and fixed-point depth ordering. Sega Rally's Model 2A geometry
uses a high-level emulation path, and the upstream driver marks `srallyc`
`MACHINE_NOT_WORKING`. These are evidence that the emulator is not a perfect
hardware reference, not evidence that this particular flicker is an emulator bug.

No exact building-window-flicker report was identified in the sources/issues
checked. The word `window` in the renderer's Z-sort notes means a render window
or viewport, not the windows of a building. Port0r also uses a custom native
Vulkan renderer, so upstream MAME's CPU-renderer behavior alone cannot establish
what the original Port0r Mac build does in this scene.

References:
- https://github.com/mamedev/mame/blob/mame0289/src/mame/sega/model2_v.cpp
- https://github.com/mamedev/mame/blob/mame0289/src/mame/sega/model2.cpp

## Packaging while macOS runners are queued

The comparison can also be produced on Linux from the exact validated IPA of
run 40317867463 (SHA-256 pinned in `repack_texture_comparison.py`). It changes
only the same two ARM64 default-value instructions and the two corresponding
ad-hoc CodeDirectory page hashes. All other payload files are byte-identical.
The script rejects identity-signed CMS signatures and verifies every code-page
hash before and after packaging, resource preservation and ZIP integrity.
This is a binary comparison package based on an already validated SDK build,
not a claim that a fresh full Xcode build ran on Linux. LiveContainer re-signs it.
