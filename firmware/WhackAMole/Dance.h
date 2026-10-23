#ifndef Dance_h
#define Dance_h

#include "Lights.h"

// ---------------------------------------------------------------------------
// The splash screen's lamp show. A pure function of time, so the caller only
// says how long the splash has been up and there is no state to reset.
//
// Three patterns in turn, each kDancePatternMs long, all following the caps
// around the ring in kChasePath order:
//   spin      -- a colour on every cap, the whole set rotating around the ring
//   flash     -- every cap on together, then off, a new colour each time
//   alternate -- every other cap on, swapping, the colour walking on
//
// `reverse` spins the other way, so the two players' rings mirror each other.
// Stages colours only; the caller flushes.
// ---------------------------------------------------------------------------
void Dance(Lights& lamps, uint32_t elapsed_ms, bool reverse);

#endif
