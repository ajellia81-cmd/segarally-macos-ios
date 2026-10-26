# R3 runtime corrections

A device R2 launch.log confirms 16-bit stereo PCM is amplified 2x (peak 0.13986 -> 0.27972), and confirms Select reaches SDL BACK (native=1 and bridge=1). R3 raises fixed PCM gain to 4x at the user's request, with no new volume option or file.

When a single SDL controller is present and Select is assigned solely to Coin, R3 routes detected Select through the original keyboard 5 Coin path. It masks native BACK during that same press to prevent duplicate coins and releases injected keys on disconnect/background. Other assignments and Guide retain their native path. Configuration is read at the press edge; missing settings use the original SELECT Coin default.

The device log also confirms haptic warm-up occurred, taking 85.5 ms; a first nonzero request arrived much later with retained stopped players. This does not prove the cause of lost physical vibration. R3 keeps a zero-intensity player running while foregrounded, so the first burst updates intensity without restarting. Zero requests silence it instead of stopping it. Background explicitly stops/invalidate players; foreground rebuilds them. Idle auto-shutdown is disabled only for these tracked engines, while the process is foregrounded.

CI tests cover queue PCM processing, Coin routing/release/rebinding, silent haptic idle/first burst/background recovery. Actual Coin behavior and first physical iPhone vibration still require a device test. No device log, ROM, raw PCM, or protected game data is included in the repository or public artifacts.
