# R7: engine-only preparation and checked real haptic playback

R6 device logs confirmed the comparison build was installed: the first real SDL rumble took 87.01 ms and 91.73 ms across two launches, while subsequent calls took 0.33–0.36 ms. First requested duration was 80 ms, intensity around 0.68–0.72, and SDL returned success. This proves a cold-call stall, not successful physical vibration. SDL records expiration after the driver returns, so these timings alone do not prove the initial pulse expired during setup.

R7 prepares only SDL's actual motor engines during controller open. A guarded initialization request constructs the engines, but the motor hook creates no player and sends/starts no playback. A zero call clears SDL's cached rumble state. This is distinct from the previous silent-player warm-up.

Real pulses use fresh continuous Core Haptics patterns with the requested intensity in the event itself. No dynamic intensity parameter is sent before start and no stopped warm-up player is reused. Equal ongoing strengths do not restart playback. Changed strengths replace the player; SDL still owns pulse duration and stop scheduling. Core Haptics create/start/stop errors are checked and logged instead of relying on SDL's unchecked start call. Engine recovery after suspension/reset is retained. Engines remain started during foreground, without silent playback.

Tests use mock engines/players and real pattern construction: no preparation playback, initial event strength, unchanged ongoing strength, changed-strength replacement, zero stop, background suppression/recovery, and create/start/stop/restart errors. Controller-open forwarding and real rumble arguments/results are tested. Select-Coin routing and fixed 4x PCM gain remain unchanged. No device log, ROM or raw PCM is published.

Physical first-pulse delivery and absence of stutter require device testing; this build is not a confirmed hardware fix.
