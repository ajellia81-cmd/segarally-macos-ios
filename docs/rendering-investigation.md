# Start-line background flicker investigation

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
