# iOS audio output

The iOS audio bridge applies a fixed 2x gain (+6 dB for quiet samples) after the game's existing volume control. There is no extra menu option or configuration file. A soft limiter bounds peaks, so loud passages may be compressed instead of hard-clipped. System volume and the existing game volume control remain effective.

Tests cover signed 16-bit and float32 PCM. Unsupported layouts pass through unchanged. Actual iPhone loudness, distortion, Select delivery and the first haptic event require device verification.
