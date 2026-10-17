#ifndef Config_h
#define Config_h

#include <Arduino.h>

// ---------------------------------------------------------------------------
// Single source of truth for every pin, timing value, and gameplay tunable.
// Nothing else in the firmware should contain a bare pin number or a magic
// duration.
// ---------------------------------------------------------------------------

// --- Build-time hardware selection -----------------------------------------
//
// The table shipped with the original build reads all of a player's buttons
// from one analog pin through a resistor ladder, and lights the dome caps with
// plain digitalWrite. The rewire replaces both. Flip these to 1 as each piece
// of hardware is actually rebuilt; the game logic above them does not change.
//
// Guarded so CI can build every combination via -DWAM_INPUT_GPIO=1 etc.
// without editing this file. See `make matrix`.
#ifndef WAM_INPUT_GPIO
#define WAM_INPUT_GPIO 0 // 0 = analog resistor ladder, 1 = one GPIO per button
#endif

#ifndef WAM_LIGHTS_PIXELS
#define WAM_LIGHTS_PIXELS 0 // 0 = digitalWrite dome lamps, 1 = WS2812 in the caps
#endif

// Bench convenience: boot straight into the debug screens instead of running
// the game. Useful when there is no display attached to answer the handshake
// and no second start button to hold.
#ifndef WAM_BOOT_TO_DEBUG
#define WAM_BOOT_TO_DEBUG 0
#endif

namespace config {

// --- Player / button counts ------------------------------------------------

// Playable mole buttons per player.
constexpr uint8_t kButtonsPerPlayer = 5;

// The start button is addressed as one index past the last mole button, so a
// single input array covers both.
constexpr uint8_t kStartButtonIndex = kButtonsPerPlayer;
constexpr uint8_t kInputsPerPlayer = kButtonsPerPlayer + 1;

// --- Display link ----------------------------------------------------------
//
// Moved off Serial2 (pins 7/8). Pin 7 is the I2S data line used by both the
// Teensy Audio Shield and a bare MAX98357A, so Serial2 and sound cannot
// coexist. Serial1 is pins 0 (RX) / 1 (TX) on the Teensy 4.1.
#define WAM_DISPLAY_SERIAL Serial1
constexpr uint32_t kDisplayBaud = 115200;

// --- Pins reserved for audio (Phase 4) -------------------------------------
//
// Not driven by this firmware yet, but claimed here so nothing else takes
// them during the rewire. Covers both candidate designs:
//   MAX98357A  : 7 (DIN), 20 (LRCLK), 21 (BCLK)
//   Audio Shield: the above plus 6, 10, 18, 19, 23
// VERIFY against the current Teensy 4.1 pinout card before soldering.
constexpr uint8_t kReservedAudioPins[] = {6, 7, 10, 18, 19, 20, 21, 23};

// --- Analog ladder input (WAM_INPUT_GPIO == 0) -----------------------------

// One analog pin per player carries that player's whole button ladder.
constexpr uint8_t kP1LadderPin = 27; // A13
constexpr uint8_t kP2LadderPin = 38; // A14

// ADC value each button settles at, in button-index order, with the start
// button last. Regenerate these with the debug mode's calibration screen
// rather than editing by hand.
//                                              B    R    W    G    Y   START
constexpr int kLadderThresholds[kInputsPerPlayer] = {440, 307, 223, 142, 687, 1023};

// Half-width of the accept window around each threshold. Must be smaller than
// half the smallest gap between adjacent thresholds or two buttons alias.
constexpr int kLadderTolerance = 20;

// Anything at or below this reads as "no button pressed".
constexpr int kLadderIdleCeiling = 20;

// --- GPIO input (WAM_INPUT_GPIO == 1) --------------------------------------
//
// Wired as switch-to-ground against INPUT_PULLUP, so no external resistors.
// Avoids 0/1 (display serial), 13 (onboard LED), and kReservedAudioPins.
//
// All twelve sit on the Teensy's LEFT pin row, in P1-then-P2 order running down
// the board. That is a stripboard decision, not an electrical one: it puts every
// signal on one side and leaves the right row carrying only VIN and GND, so the
// ribbon to the button board gathers from a single column instead of jumping
// across under the Teensy. Pins 24-32 are on the lower half of that same left
// row, not in the bottom cluster.
// They run in one unbroken block down the left row: pins 9 through 32, skipping
// only pin 10 (reserved) and the 3.3 V pin. Those two gaps fall INSIDE the block,
// which is the point -- twelve inputs plus two unusable positions is exactly the
// fourteen contiguous strips a 1x14 ribbon header spans, so every switch signal
// reaches its Teensy pin along its own strip with no jumper. The two dead strips
// get cut away from the Teensy and reused for the ribbon's ground and pixel data.
//                                                     B   R   W   G   Y  START
constexpr uint8_t kP1ButtonPins[kInputsPerPlayer] = {9, 11, 12, 24, 25, 26};
constexpr uint8_t kP2ButtonPins[kInputsPerPlayer] = {27, 28, 29, 30, 31, 32};

// --- Dome lamp output (WAM_LIGHTS_PIXELS == 0) -----------------------------
//
// The start buttons are not lit in the original build, so these arrays cover
// mole buttons only.
//                                                   B   R   W   G   Y
constexpr uint8_t kP1LedPins[kButtonsPerPlayer] = {28, 29, 30, 31, 32};
constexpr uint8_t kP2LedPins[kButtonsPerPlayer] = {37, 36, 35, 34, 33};

// --- WS2812 output (WAM_LIGHTS_PIXELS == 1) --------------------------------
//
// Use the WS2812Serial library, not Adafruit_NeoPixel or FastLED: the
// bit-banging drivers disable interrupts for the length of the frame, which
// jitters the display link and will audibly glitch audio in Phase 4.
//
// WS2812Serial can only drive a serial-TX-capable pin. Pin 8 is Serial2 TX and
// is on the library's supported list for the Teensy 4.1 (verified against
// WS2812Serial.cpp in Teensyduino 1.60.0).
//
// Chosen because it sits one strip ABOVE the twelve button inputs, so the
// ribbon header's fourteen strips stay unbroken for the switches and the level
// shifter sits clear of them at the top of the board.
//
// Caveat: pin 8 is the audio shield's I2S input (IN1). This game only ever plays
// audio out, so nothing collides -- but anything wanting audio IN would have to
// move the pixel data to another WS2812Serial pin.
//
// Teensy 4.1 runs 3.3 V logic. WS2812Bs nominally want 0.7*VDD on data, so put
// a 74AHCT125 level shifter between this pin and the first pixel.
constexpr uint8_t kPixelDataPin = 8;

// Pixels in each dome cap: a 12-pixel WS2812 ring in the plunger cavity.
// See hardware/button-led-carrier.scad.
constexpr uint8_t kPixelsPerButton = 12;

// Chain order is P1's five mole caps, then P2's five. The two start buttons are
// plain arcade buttons with no lamp, so they contribute a switch and nothing
// else -- they are not in the pixel chain and get no pixels allocated.
constexpr uint16_t kPixelCount = kButtonsPerPlayer * 2 * kPixelsPerButton;

// Global ceiling, 0-255.
//
// 120 pixels at full white is ~7.2 A, far past the 15 W (5 V, 3 A) the power
// bank delivers. During play only two caps are lit, so real draw is near 1 A;
// the worst case is the debug mode's ALL-ON screen. At 64/255 that screen pulls
// ~1.8 A. With the LED panel, the Matrix Portal S3 and the Teensy the whole
// table peaks near 2.5 A -- roughly 18% headroom on the 3 A supply.
//
// WS2812 output is linear in PWM but perception is not, so this reads only
// slightly dimmer than the 80 it replaced. Raise it only after measuring the
// rail on the ALL-ON screen. docs/wiring.html records why the supply is 5 V
// direct with no buck converter, and what that ceiling costs.
constexpr uint8_t kPixelBrightness = 64;

// --- Randomness ------------------------------------------------------------

// Unconnected pin, read once at boot to seed the PRNG.
constexpr uint8_t kFloatingSeedPin = 17;

// --- Loop timing -----------------------------------------------------------

// Inputs are polled every pass through loop(); game logic advances on this
// interval. Nothing in the firmware calls delay().
constexpr uint32_t kTickIntervalMs = 10;

// A press must read stable for this long before it counts.
constexpr uint32_t kDebounceMs = 25;

// --- Gameplay tunables -----------------------------------------------------

// Points awarded for an instant hit. Decays linearly to zero across
// kMoleLifetimeMs, at which point the mole moves on by itself.
constexpr int kMoleStartingPoints = 1000;

// Preserves the original build's decay rate of one point per 20 ms.
// Worth shortening once you have the debug mode to retune against; 20 seconds
// is a long time for a single mole to stay up.
constexpr uint32_t kMoleLifetimeMs = 20000;

// Deducted for hitting a lit-up player's wrong button. The score floors at
// zero rather than refusing to apply below this value.
constexpr int kWrongButtonPenalty = 500;

// Blink period of the currently-lit mole cap.
constexpr uint32_t kLedBlinkMs = 200;

// --- Debug mode ------------------------------------------------------------

// Hold both start buttons together for this long during attract mode to enter
// the debug menu, and again to leave it.
constexpr uint32_t kDebugEntryHoldMs = 2000;

// Dwell per colour step in the LED walk screen. Each cap shows every colour in
// turn before the walk moves on, so one full sweep is this times the number of
// colours times the number of caps -- about twelve seconds as configured.
constexpr uint32_t kDebugLedWalkMs = 300;

// Samples averaged per button on the calibration screen.
constexpr uint8_t kCalibrationSamples = 32;

// How long a lone start press waits before it is allowed to start a game.
//
// Both start buttons together are the debug gesture; either one alone starts a
// game. No two fingers land on the same millisecond, so acting on the first
// press the instant it latches takes the state machine out of attract mode
// before the second button has even been polled -- which made the debug combo
// unreachable from attract mode entirely. Holding a lone press for this long
// gives the second button time to arrive.
//
// Floor is kDebounceMs; a deliberate two-handed press is usually within 100-200
// ms, so this leaves margin. It is also the delay a player feels between
// pressing start and seeing READY, which is why it is not larger.
constexpr uint32_t kStartArbitrationMs = 300;

} // namespace config

#endif
