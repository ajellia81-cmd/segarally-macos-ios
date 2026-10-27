# R9: finite real playback priming before gameplay

R8 device logs confirm that the first real rumble was extended from 110 ms to 250 ms and stopped about 256 ms after its successful start. The user still felt no first vibration. R8's duration-extension comparison therefore did not fix the omission. R9 removes the extension and restores every real game's requested rumble duration.

R7's engine preparation remains: native SDL creates/starts its actual engines at controller open while the motor hook suppresses initialization playback. R9 then starts a separate, finite Core Haptics continuous event at intensity 0.10 and duration 0.020 seconds once per tracked motor. Unlike previous silent-player attempts, this is a real nonzero output request. It may be felt as a weak startup tick. The user explicitly approved the startup priming approach.

The priming player is never stored as SDL's game player and is not counted as a game haptic request. Its finite event ends independently of SDL polling. A delayed identity-checked release holds the player briefly but cannot stop or clear a later game player. An overlapping real game request stops only the priming player first, then starts the original requested game strength. Engine reset clears the priming reference. Cleanup cancels priming; normal background return does not replay successful priming. Failed priming is logged and does not mark that motor ready.

Tests use real pattern construction with mock hardware: initial 10%/20ms pattern, one-time priming, separate game-player state, overlap cancellation, stale completion safety, failed priming retry, engine recovery and playback errors. SDL wrapper tests verify the first real duration is restored unchanged and no extra native calls occur on real requests. Existing Select-Coin and fixed 4x audio remain unchanged.

This tests whether real playback initialization can absorb the first missing output at startup. The cause of physical omission is still unproven, and only device testing can establish whether the first game vibration arrives without stutter. No device log, ROM, protected data or raw PCM is published.
