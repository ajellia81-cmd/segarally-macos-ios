# R10 comparison: stronger finite priming and engine lifecycle diagnostics

R9 device logs confirm both 10%/20ms priming players returned start success at 09:46:07.710. The first game pulse followed about 35.4 seconds later, at strength 0.7098 and duration 80 ms; it started successfully in 1.56 ms and stopped about 82 ms later. The user felt neither startup priming nor the first game pulse. The R9 segment contains no second game pulse. API success is not proof of physical output.

R10 changes the separate startup priming pattern to intensity 0.70 and duration 0.120 seconds, comparable to a game impact. It may produce a noticeable startup vibration. The pattern is finite independently of SDL polling, and its identity-checked retained lifetime now exceeds its duration (500 ms). It is not reused as SDL's game player, and an overlapping game request cancels only the priming player.

Stopped/reset callbacks now log motor, engine, stopped reason and foreground state before invalidation/recovery. Previous logs did not record these callbacks, so their absence could not establish that engines stayed running between startup and gameplay.

Engine creation still runs at controller open to preserve the user-confirmed stutter improvement. Every real game rumble retains its requested strengths/duration; R8's duration extension remains removed. Select-Coin and fixed 4x audio are unchanged. Mock tests verify the actual 70%/120ms pattern, isolation from game playback, stale completion protection, one-time behavior and playback/recovery errors.

This is a comparison build, not a confirmed fix. Device checks should separately record whether startup priming is felt, whether the first game vibration arrives, and whether stutter returns. A missing startup sensation alone cannot show that priming failed, because the first physical output may itself be discarded. No device log, ROM, protected game data or raw PCM is published.
