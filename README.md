# Port0r Rally: experimental iOS / LiveContainer conversion

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

**Installation and launch on an iPhone 18 Pro Max / iOS 27 have not been tested.**
A successful Actions run establishes conversion and package checks only.

After launch creates the directories, put your legally obtained game files in
the guest app's **Documents/Port0r/srallyc/roms** directory through LiveContainer's
container/file management. Keep the ZIP files compressed. The conversion no longer
creates an additional Downloads folder or redirects the Mac Downloads path.
An empty Documents/Downloads folder left by earlier builds is removed at startup;
if it contains files, it is preserved to avoid deleting user data.
The original engine expects `srallyc.zip` and `segabill.zip` for MAME 0.289.
If the guest Documents directory is not visible in Files, open it through
LiveContainer. File sharing keys alone do not guarantee guest visibility.
ROM discovery on device remains unverified.

## Display, input and sound

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
  unverified. A touch-only driving overlay has not been implemented.
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
