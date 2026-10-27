# R12: remove the native first-knock discard

Device testing showed startup and race-entry priming were felt but did not prevent the first collision's missing vibration. Waiting 40 seconds after subsequent collisions did not reproduce the omission. Priming is therefore removed; normal controller-open engine preparation remains to preserve the stutter improvement.

The pinned Port0r main executable explicitly discards the first changed knock sequence when its previous sequence is zero. At VA 0x100011528 it reads the knock sequence/strength/kind, compares sequence equality, then loads the saved previous sequence from app-object offset 0x1f4. At 0x10001155c, cbz w8, 0x1000115f0 skips SDL rumble when that previous sequence is zero; 0x1000115f0 still stores the new sequence. Fake SDL/Core Haptics pulses do not change this application-side knock sequence, explaining why those experiments cannot bypass this condition.

R12 replaces only that four-byte cbz instruction with nop. A 220-byte surrounding-code guard rejects unexpected executable versions. Equality filtering still rejects sequence 0->0 and unchanged sequences. Existing haptics-enabled, menu-closed and live-game gates remain unchanged. Strength conversion, 80/110ms event durations, per-controller iteration and recording of the latest sequence are unchanged.

The regression test runs the actual guarded ARM64 instruction slice in Unicorn, with controlled app/stack/controller memory and deterministic knock/SDL call hooks. The original code reproduces no output for sequence 0->1 while recording 1. The patched code emits one request per controller for that event. Both variants preserve later 80/110ms requests, unchanged/zero sequences, menu/disabled/inactive gates and empty-controller behavior. Original/prepared/converted code validation ensures only the allowed instruction is changed alongside the existing Guide patch.

All startup and race-entry playback priming has been removed. The R11 telemetry observer, native getter ABI header and race-only controller lifetime wrappers are removed. Select-Coin, fixed 4x audio, engine preparation/recovery, touch controls and original rendering remain. No raw device log, ROM or protected game data is published.

This identifies and reproduces a native application-side first-event discard. Physical delivery of the first collision vibration still requires device testing; CI emulation does not constitute iPhone execution.
