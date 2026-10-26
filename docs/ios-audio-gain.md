# iOS audio output

R3 applies a fixed 4x PCM gain (+12 dB for quiet samples), twice R2's 2x gain. There is no extra menu option or configuration file. A soft limiter bounds peaks, so loud passages may be compressed instead of hard-clipped. System volume and the existing game volume control remain effective.

R3 changes audio gain only. Select and first-vibration issues remain unresolved on the device. The existing A/S/H diagnostic counters and guest launch log are retained. The visible R3 label and build version 1026.3 identify the installed build.

Tests cover signed 16-bit and float32 PCM, including the queue creation/enqueue wrapper path. Device output level and physical input/haptic delivery require a new device launch.log.
