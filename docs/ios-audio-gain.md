# R8 comparison: extend only the first finite real rumble

R7 device testing confirmed that cold-call stutter is resolved but the first physical vibration is still missing. In two new launches, engine-only preparation took 86.00 ms and 71.51 ms before the first game pulse. First real calls took 0.95 ms and 1.48 ms; both motor players reported start success at strength about 0.66 and stop success about 82 ms later. Subsequent 80 ms pulses also reported success and were felt. These API results do not prove physical actuator output or identify its latency.

R8 tests the hypothesis that cold physical playback needs more time than the first short pulse. The first finite nonzero SDL controller-rumble request per process is extended to at least 250 ms. Its low/high strength is unchanged. No synchronous delay, extra playback, replay or retry is introduced. A failed native call returns its error and leaves the extension available for the next request. Zero stops, duration-zero requests, later pulses and already-long first pulses retain their durations. Background return and controller reopen do not reset this one-time comparison.

R7's engine-only preparation and checked fresh-pattern playback remain unchanged; no silent-player warm-up is restored. Select-Coin routing and fixed 4x PCM gain are preserved. The R7-named preparation export remains the internal ABI; logs/HUD and package metadata identify R8.

Mock tests cover initial zero stop, failed first pulse, successful first extension, subsequent strengths/durations, long first pulse, duration-zero requests and exact native call count. Existing motor tests still cover no preparation playback, start/stop/create/restart errors and lifecycle recovery.

This is a diagnostic comparison, not a confirmed physical fix. The first pulse can now feel longer if it is delivered. Device testing must check presence of the first vibration and whether any stall returns. No device log, ROM, protected game data or raw PCM is published.
