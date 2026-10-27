# Maintained iOS adaptations

The build uses official Port0r Mac v0.1.0 and converter commit
c2562a333d4de4c08da4ceb4a4f1485bddb84e04, with no game ROMs or optional asset packs.

The native first-collision correction replaces the guarded instruction at
0x10001155c from `cbz w8, 0x1000115f0` to `nop`. The original branch saved the
first changed knock sequence without requesting SDL rumble when the previous
sequence was zero. The patch keeps duplicate filtering, haptics/menu/live-game
gates, strength conversion and event durations. An isolated ARM64 regression test
reproduces the upstream discard and verifies the corrected path. The user confirmed
physical first-collision delivery in R12.

The original native Guide selection, fixed iOS window/display behavior, audio gain,
ROM import aliases, Select-Coin bridge, touch controls and lifecycle recovery remain.
No synthetic startup/race-entry vibration remains.

Release cleanup removes FPS and statistics components, runtime counters and PCM
probes, trace-only hooks, shader dumps and launch-log capture. The functional
CADisplayLink refresh request is separate from any visual/debug overlay. A narrow
upgrade cleanup removes only known port-generated launch logs/shader dumps and
empty directories, preserving unknown content and game data.

Packaging strips only local/debug symbols, checks that exported symbols and the
native first-collision/Guide edits survive, re-signs ad-hoc, uses level-9 ZIP
compression, then extracts and verifies the actual IPA. Marketing-size icon output
is omitted; device-size icons and component license notices remain. Regression
tests and validation reports are build-time artifacts, never app payload.
