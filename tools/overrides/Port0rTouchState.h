#pragma once
#include <stdbool.h>
#include <stdint.h>
typedef void (*Port0rTouchEmit)(unsigned short, bool);
typedef struct { unsigned short held[128]; bool enabled; } Port0rTouchState;
static inline void Port0rTouchSetEnabled(Port0rTouchState *state, bool enabled, Port0rTouchEmit emit) {
    if (!enabled) {
        for (unsigned short key = 0; key < 128; ++key) {
            if (state->held[key]) { state->held[key] = 0; emit(key, false); }
        }
    }
    state->enabled = enabled;
}
static inline void Port0rTouchChange(Port0rTouchState *state, unsigned short key, bool down, Port0rTouchEmit emit) {
    if (!state->enabled || key >= 128) return;
    if (down) {
        if (state->held[key] == UINT16_MAX) return;
        if (state->held[key]++ == 0) emit(key, true);
    } else if (state->held[key] && --state->held[key] == 0) emit(key, false);
}
