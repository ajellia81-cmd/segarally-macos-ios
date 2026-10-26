# iOS audio gain

The iOS output bridge applies 2x (+6 dB for quiet samples) gain after the game's existing volume control. A soft limiter bounds peaks; loud passages may be compressed. No microphone or system volume changes are used.

After first launch, edit `Documents/Port0r/audio-gain.txt` to a number from `1.0` to `4.0`, then restart the game. `1.0` bypasses sample processing and preserves original PCM. The default is `2.0`; try `3.0` or `4.0` for more amplification. Unsupported PCM layouts pass through unchanged.

Cloud tests cover signed 16-bit and float32 processing. Actual iPhone loudness, distortion and controller delivery require device verification.
