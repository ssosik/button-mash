#include "Lights.h"

// --- Lights -----------------------------------------------------------------

void Lights::SetAll(Color color) {
  for (uint8_t i = 0; i < config::kButtonsPerPlayer; i++) {
    Set(i, color);
  }
  Show();
}

// --- DigitalLights ----------------------------------------------------------

DigitalLights::DigitalLights(const uint8_t pins[config::kButtonsPerPlayer]) : _pins(pins) {}

void DigitalLights::Begin() {
  // The original code ran this loop in the constructor against an
  // uninitialized _numled, so the lamps were never reliably driven low at
  // startup. Doing it from setup() with a compile-time count fixes both halves.
  for (uint8_t i = 0; i < config::kButtonsPerPlayer; i++) {
    pinMode(_pins[i], OUTPUT);
    digitalWrite(_pins[i], LOW);
  }
}

void DigitalLights::Set(uint8_t index, Color color) {
  if (index >= config::kButtonsPerPlayer) {
    return;
  }
  digitalWrite(_pins[index], color.IsOff() ? LOW : HIGH);
}

// --- PixelLights ------------------------------------------------------------

#if WAM_LIGHTS_PIXELS
#include <WS2812Serial.h>

namespace {
// Buffer sizes are fixed by the library: 12 bytes per pixel for the DMA
// display buffer (which must live in DMAMEM so the DMA engine can reach it)
// and 3 bytes per pixel for the drawing buffer. See the library's BasicTest
// example -- these are not arbitrary.
DMAMEM byte g_pixel_display[config::kPixelCount * 12];
byte g_pixel_drawing[config::kPixelCount * 3];

WS2812Serial g_chain(config::kPixelCount, g_pixel_display, g_pixel_drawing, config::kPixelDataPin,
                     WS2812_GRB);

// Set by either player's instance, cleared by whichever one transmits. One
// chain carries both players, so one flag is enough, and it makes a Show() with
// nothing new to send free.
bool g_dirty = false;
} // namespace

PixelLights::PixelLights(uint16_t first_pixel, bool owns_chain)
    : _first_pixel(first_pixel), _owns_chain(owns_chain) {}

void PixelLights::Begin() {
  if (!_owns_chain) {
    return;
  }
  g_chain.begin();
  g_chain.setBrightness(config::kPixelBrightness);
  g_chain.clear();
  g_chain.show();
}

void PixelLights::Set(uint8_t index, Color color) {
  if (index >= config::kButtonsPerPlayer) {
    return;
  }

  const uint16_t base = _first_pixel + (uint16_t) index * config::kPixelsPerButton;
  for (uint8_t p = 0; p < config::kPixelsPerButton; p++) {
    g_chain.setPixel(base + p, color.r, color.g, color.b);
  }
  g_dirty = true;
}

void PixelLights::Show() {
  // Either instance may flush. This used to be owner-only, so P2's changes
  // reached the caps only when P1 next happened to call Show() -- up to a
  // blink period late, and never at all in a P2-only game, where P1 is not
  // ready and never calls it.
  if (!g_dirty) {
    return;
  }
  g_dirty = false;
  // show() waits internally for any prior DMA transfer to drain, so it is safe
  // to call every tick. (The library declares busy() but never defines it, so
  // it cannot be used as a guard.)
  g_chain.show();
}
#endif
