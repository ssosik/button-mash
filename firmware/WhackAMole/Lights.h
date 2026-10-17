#ifndef Lights_h
#define Lights_h

#include "Config.h"
#include <Arduino.h>

// ---------------------------------------------------------------------------
// One player's button lamps, behind an interface that hides whether they are
// plain on/off dome lamps or addressable pixels in the caps.
//
// Colour is carried through even in the on/off implementation, which simply
// treats "not black" as on. That way Phase 3 gains colour without any game
// logic changing.
// ---------------------------------------------------------------------------

struct Color {
  uint8_t r, g, b;

  constexpr bool IsOff() const { return r == 0 && g == 0 && b == 0; }
};

namespace colors {
constexpr Color kOff = {0, 0, 0};
constexpr Color kWhite = {255, 255, 255};
constexpr Color kMole = {255, 200, 40};  // lit mole cap
constexpr Color kHit = {0, 255, 60};     // brief flash on a correct hit
constexpr Color kMiss = {255, 0, 0};     // brief flash on a wrong button

// Primaries, used only by the debug walk. Driving each channel on its own is
// what distinguishes a dead colour from a dead pixel, and catches a ring wired
// for a different byte order -- neither of which a white-only test can show.
constexpr Color kRed = {255, 0, 0};
constexpr Color kGreen = {0, 255, 0};
constexpr Color kBlue = {0, 0, 255};
} // namespace colors

class Lights {
public:
  virtual ~Lights() = default;

  // Configure pins. Must be called from setup(), never from a constructor.
  virtual void Begin() = 0;

  // Stage a colour for one button. Nothing reaches the hardware until Show().
  virtual void Set(uint8_t index, Color color) = 0;

  // Push staged colours to the hardware.
  virtual void Show() = 0;

  void SetAll(Color color);
  void Clear() { SetAll(colors::kOff); }
};

// --- Plain on/off dome lamps ------------------------------------------------
class DigitalLights : public Lights {
public:
  explicit DigitalLights(const uint8_t pins[config::kButtonsPerPlayer]);

  void Begin() override;
  void Set(uint8_t index, Color color) override;
  void Show() override {} // digitalWrite is immediate

private:
  const uint8_t* _pins;
};

#if WAM_LIGHTS_PIXELS
// --- WS2812 pixels in the caps ----------------------------------------------
//
// Both players share one physical chain on one pin, so each instance writes
// into a slice of a single shared buffer. Only the owner initializes the chain,
// but either may flush it: Show() sends whatever either player has changed.
class PixelLights : public Lights {
public:
  // `first_pixel` is this player's offset into the shared chain.
  PixelLights(uint16_t first_pixel, bool owns_chain);

  void Begin() override;
  void Set(uint8_t index, Color color) override;
  void Show() override;

private:
  uint16_t _first_pixel;
  bool _owns_chain;
};
#endif

#endif
