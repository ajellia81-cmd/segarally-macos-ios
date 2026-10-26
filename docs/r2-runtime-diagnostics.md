# R2 runtime investigation

The user reports no device change in Select, loudness, or first vibration with the prior IPA. Prior CI tests and shipped symbol checks prove packaging and simulated behavior, but do not prove that the device invoked those paths.

R2 keeps fixed 2x PCM gain and the existing haptic correction. It adds a visible R2 identifier and counters: A = AudioQueue enqueue calls, S = SDL BACK reads, H = non-warm-up positive SDL motor requests. These counters are invocation evidence, not evidence of audible output, button detection, or physical vibration. Zero H with physical phone vibration indicates the SDL motor hook is not observing that vibration path. No game audio or ROM data is recorded.

Select no longer requires the manufacturer name when exactly one SDL joystick and one GameController device exist. It reads both Options and Share even when an Options object exists. Ambiguous unnamed multi-controller setups retain native behavior. Guide stays unchanged.

The launch log records the first nonzero PCM block's peak before/after gain, actual format/flags, SDL names, Select native/bridge state changes, and the first four haptic request states. Logs are bounded; no raw PCM is saved. Application version 1026.2 and the R2 HUD identify the installed code.

Actual device behavior remains unverified. A new guest launch.log is needed to distinguish inactive hooks, identity differences, output signal limits, and a separate phone-haptic path. ARM64 parser execution remains skipped on Intel CI; the unchanged parser was executed on the earlier ARM64 build.
