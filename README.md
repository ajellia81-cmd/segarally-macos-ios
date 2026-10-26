# Sega Rally Championship: experimental iOS / LiveContainer conversion

GitHub Actions converts the official **mac-v0.1.0 ARM64** engine with
[`macos-on-ios-public`](https://github.com/zorrobyte/macos-on-ios-public), pinned
to `c2562a333d4de4c08da4ceb4a4f1485bddb84e04`. No local Mac or Apple developer
credentials are used. This is an experimental binary conversion, not an iOS
source port. Port0r's source is not public.

## Download and install

Open the latest successful [conversion run](https://github.com/ajellia81-cmd/segarally-macos-ios/actions/workflows/ios-conversion.yml)
and download **SegaRally-LiveContainer-UNSIGNED**. Extract the artifact ZIP and
import the `.ipa` into LiveContainer. The IPA has ad-hoc signatures for binary
integrity only, no Apple certificate or provisioning profile. LiveContainer
must perform its normal signing/import process.

**A user device test reached the original ROM setup screen on iPhone / iOS 27.**
Actual ROM import, gameplay, audio, controller input and refresh rate still need
device verification. Actions validates conversion and packaging only.

Put your legally obtained `srallyc.zip` and `segabill.zip` (MAME 0.289) in the
guest app's **Documents/Downloads** directory, without extracting them, through
LiveContainer's container/file management. Return to the game so its original
Downloads scanner can find and import them. The original setup-screen wording
is preserved.

The Mac `~/Downloads` path is mapped to this guest folder. A home-directory
Downloads symlink is created when absent so Foundation and native filesystem
scanners see the same folder. Existing directories, ROMs and imported game data
are preserved. Original imported data remains under
**Documents/Port0r/srallyc**; users need not populate its internal roms folder
manually. The old empty-Downloads cleanup has been removed.

If the guest Documents directory is not visible in Files, open it through
LiveContainer. File sharing keys alone do not guarantee guest visibility.
Diagnostic output is saved to **Documents/Port0r-diagnostics/launch.log**.

Both native `~/Downloads` and `~/Library/Application Support/Port0r` are now
aliased to their Documents counterparts. This also covers libc++ filesystem
enumeration/copy operations which bypass libc path shims. Existing native
directories are merged without replacing destination files, then kept as
`.before-ios-paths` backups. A failed alias operation restores the native folder.
The build checks a real C++ file copy through these aliases using placeholder
text, never ROM data. Actual on-device ROM recognition still needs verification.

The app uses the supplied Sega Rally logo/car image as its iOS icon and the
display name **Sega Rally Championship**. The bundle ID is unchanged so an
in-place LiveContainer update can retain the guest data.

## Touch controls and background behavior

Touch controls appear only when no GameController gamepad is connected. They
provide steering/menu directions, gas, brake, gears, view, coin, start and menu
through the original keyboard mappings. They support simultaneous presses;
connecting a gamepad, cancelling a touch or leaving the app releases held inputs.
This version uses digital steering/throttle, not analog touch controls. UI
placement, actual input delivery and hot-plug visibility require a device test.

MoltenVK command submission pauses when the app loses foreground activity,
then resumes on activation. This targets the observed background
`VK_ERROR_DEVICE_LOST` error; it does not permit GPU work in the background.
The runtime hook is scoped to MoltenVK callers and leaves host/UIKit rendering
alone. Background/foreground recovery needs an on-device test.

## Display, input and sound

The user has confirmed ROM-based gameplay and a full-width iPhone picture.
Audio and Backbone Pro Select support are being adapted to the iOS default
audio route and controller system-gesture handling; their latest fixes still
need device verification.

Desktop fullscreen/window-resize requests are ignored on iOS, where the guest
window already fills the screen. The original menu entry remains visible but
cannot switch display modes. On launch only `flat.fullscreen` is reset to zero,
with a one-time settings backup; other settings and ROM data are preserved.
The original Mac SDL 2.30.3 API table is version/size checked before enabling
this policy; all non-window APIs keep their original implementations.

The top-left performance overlay updates once per second:

- **Present**: completed Metal presentations per second, including repeated
  arcade frames; this is the useful value for testing the 60/120 fps option.
- **Render**: Metal drawable acquisitions per second; not an emulation counter.
- **Game FPS --**: the internal MAME frame counter cannot currently be measured
  safely through a documented ABI. A constant 60 is not shown as measured data.
- **Output**: final drawable pixel dimensions, not the supersampled internal
  3D render-target dimensions.

Compare the same scene with the same settings except the option being tested.
Real 120 Hz output, audible sound and Backbone button delivery require a device
test; build-time tests do not establish those outcomes.

- Original resolution choices remain in the unmodified engine: Auto, 50%, 75%,
  100%, 150% and 200%. Native size comes from `UIScreen.nativeBounds`, with the
  actual screen scale, including iPhones with a 3x scale. This adds adaptation
  to the target device; it does **not** add a new named item to the closed-source
  game's settings menu. No unverified iPhone pixel dimensions are hard-coded.
- Landscape orientations and the engine's original widescreen renderer are
  retained. Safe-area/HUD placement needs a device test.
- High-refresh permission is enabled on iPhone; display APIs report the actual
  maximum refresh rate. Select 120 in the original frame-rate menu on a capable
  device. This is **not a measured 120fps result**. The original engine displays
  each 60fps arcade frame twice at 120Hz, without frame interpolation.
- ExtendedGamepad is declared and SDL's existing GameController/MFi backend is
  enabled; Mac IOKit/HID backends are disabled. Pair a controller with iOS before
  launch. Original mappings: A start, View/Select coin, Menu pause/settings,
  RT/LT gas/brake, left stick steer, RB/LB gears, Y view. Input and rumble are
  unverified. A digital touch driving overlay is supplied when no pad is connected.
- Original MoltenVK renderer, engine library, audio code and graphical settings
  are retained. Compatibility stubs remain and may prevent launch, rendering,
  audio or controller functionality. Diagnostic artifacts contain generated
  shim sources so missing functions can be identified without shipping ROMs.
- Mac ffmpeg recording and Mac self-updates are not supported. Networking stays
  blocked by the converter, including leaderboard/update requests. Metal HUD
  is disabled to avoid permanent debug overlays.

## What the build validates

The release archive is SHA-256 pinned. Preparation rejects unexpected release
files and removes optional `Resources/srallyc` cockpit packs. Packaging requires
successful conversion, ARM64-only Mach-O files with iOS platform tags, no
encrypted binaries, no direct AppKit dependency, valid ad-hoc signatures and a
readable `Payload/SegaRally.app` IPA. Empty provisioning profiles and placeholder
team entitlements are removed. `validation.json` records dependencies and IPA
SHA-256. These are static checks, not an iOS execution test.

No ROMs, BIOS archives, HD textures or cockpit packs are included in the
repository or new IPA artifacts. The engine is fetched from its official
release only during Actions. Component notices and the compatibility layer's
MIT license are retained in the app. Sega Rally and all trademarks belong to
their respective owners; this project is unaffiliated.
