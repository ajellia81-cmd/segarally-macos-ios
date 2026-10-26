# R6: warm-up-off comparison for first-vibration omission

The user recalls the omission starting with the first-stutter optimization. Commit dce8573ac14f71a5ae968c622ac72b26a08ac8a7 (parent e0356211996e21d1930db5be485f7a069b63b1a9) introduced SDL controller-open rumble priming and suppression of its nonzero intensity. R4/R5 retained that mechanism; neither removed the omission on device.

R6 removes synthetic rumble, silent-player preparation, controller-open priming, and the post-start intensity rewrite. Cold foreground requests go to the original SDL motor with their original intensity. Stop requests keep original SDL behavior. The background suppression and engine-retention/restart fixes remain; recovery restarts only the engine and leaves player creation to original SDL on an actual nonzero request.

A pass-through SDL rumble wrapper records the first eight real calls' requested strengths, duration, native result and execution time without changing arguments or making extra calls. Tests assert no startup calls/player creation and exact forwarding of the first real request, stop requests and native errors. Select-Coin routing and fixed 4x PCM gain are preserved.

This is a comparison build, not a confirmed fix. The old first-vibration stutter may return. Device testing must separately record whether the first vibration is present and whether it stalls. No device log, ROM, protected game data or raw PCM is published.
