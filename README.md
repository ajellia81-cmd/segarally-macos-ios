# Sega Rally Championship — iOS / LiveContainer

Port0r's official macOS ARM64 build converted for iOS using the pinned
[macos-on-ios-public](https://github.com/zorrobyte/macos-on-ios-public) compatibility layer.
The app is named **Sega Rally Championship** and uses the user-supplied Sega Rally artwork.

## Install and game files

Download the **SegaRally-LiveContainer-UNSIGNED** artifact from a successful
[GitHub Actions build](https://github.com/ajellia81-cmd/segarally-macos-ios/actions).
Extract the artifact ZIP and import its IPA into LiveContainer. The IPA has an ad-hoc
signature, no Apple developer identity or provisioning profile; LiveContainer supplies
its signing context.

No ROM, soundtrack or optional game-asset pack is included. Place your own matching
**MAME 0.289** `srallyc.zip` and `segabill.zip` archives in the guest's
**Documents/Downloads** folder, unextracted. They are imported into
**Documents/Port0r/srallyc/roms**. Settings and saves stay under
**Documents/Port0r/srallyc**. Existing imports and migration backups are preserved.

## iOS behavior

- Native device resolution and the original percentage-based resolution options.
- Native maximum refresh request, including 120Hz on capable devices. The original
  engine can show an arcade frame more than once; display refresh is not a measurement
  of unique emulated frames.
- Desktop fullscreen/window resizing blocked to avoid the resolution regression.
- Widescreen, native gamepad input, Guide in the original button-selection list,
  and the working sole Select-to-Coin binding.
- Touch buttons appear only without a connected gamepad.
- Audio follows the iOS media route, with the established fixed 4x gain and peak limiter.
- Background gameplay/audio pause and foreground recovery.
- Controller engine preparation without synthetic playback, and the confirmed native
  first-collision fix. See [porting notes](docs/porting-notes.md).

## Release cleanup

The release has no added FPS/HUD, invocation counters, PCM peak probes, performance
statistics, method/controller tracing, shader dumps or launch-log capture. High-refresh
display requests remain active without an overlay. Earlier port-generated launch logs
and shader dumps are removed on first launch; unknown files, ROMs, settings and saves
are preserved.

Runtime shim sources are optimized for size. Local/debug symbols are stripped while
exported symbols and native fixes are checked, and the IPA uses maximum ZIP deflate
compression. Required component license notices are included.

## Build and verification

The main workflow downloads the checksum-pinned official Port0r Mac release, pins the
converter, builds iOS ARM64 shims with an available iOS 26+ SDK, runs regression checks,
and packages a ROM-free IPA. CI checks run only on GitHub Actions; tests, source files,
logs and reports are not shipped inside the IPA. A separate build-validation artifact
contains reports.

The first-collision correction was confirmed by the user on their device in R12.
The cleaned release still needs its own physical-device confirmation. CI validates
code paths and package structure; it does not launch the game on an iPhone.

Port0r's rendering and optional features remain subject to the upstream engine.
