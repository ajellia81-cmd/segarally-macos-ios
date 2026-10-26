# R5: isolate first cold-start haptic output from warm-up

The user confirmed R4 restores normal vibration and that the omission occurs only once after a fresh application launch. R5 changes only the prepared player's ownership: the actual SDL motor engine and pattern are warmed with a disposable zero-intensity player, which is stopped/cancelled; a separate fresh output player is created on that same engine before gameplay. The real output player has never started/stopped or received a zero-intensity dynamic parameter before its first request.

R4 stop behavior, foreground/background recovery, Select-Coin keyboard routing and fixed 4x audio gain are preserved. The rejected continuously running silent-player design is not used. CI checks that a fresh output has no warm-up parameter/start history, and retains first-request intensity and recovery tests. This tests implementation/state, not physical vibration. Device confirmation remains required; no root cause or physical fix is claimed.

No ROM, protected game asset, raw PCM or device launch log is published.
