# R4: restore working vibration baseline

The user confirmed R3 Select and audio work, but reported all physical vibration disappeared. R4 restores AppKit_Haptics.m exactly to the R2 implementation at d915acf044ee21e5898d1ec56f6a12beb48ce1ce. This removes the foreground continuously running silent player, interception of zero-intensity stop requests, and changes to auto-shutdown. Previous stopped-player warm-up and background recovery are restored.

The verified working Select-to-keyboard-Coin route and fixed 4x audio gain from R3 are unchanged. Only the haptic portion of the native smoke test is restored; current Select routing/configuration tests remain enabled. R4 build identifier is 1026.4.

This is regression recovery, not a claim to solve the original first-vibration omission. Before R3 the user reported the first vibration missing and later vibrations working. R4 requires device confirmation of restored vibration; the original first-event issue remains unresolved. No ROM or protected game assets are included.
