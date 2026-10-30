// Whack A Mole Attack -- Teensy 4.1 controller.
//
// The Teensy owns the game: it reads the buttons, drives the button lamps, and
// sends state messages over a serial link to a Matrix Portal S3, which does
// nothing but render what it is told (see display/code.py).
//
// Every pin, timing value, and gameplay tunable lives in Config.h.

#include "ButtonInput.h"
#include "Config.h"
#include "Game.h"
#include "Lights.h"
#include "Player.h"

// --- Input hardware ---------------------------------------------------------
#if WAM_INPUT_GPIO
GpioInput p1_input(config::kP1ButtonPins);
GpioInput p2_input(config::kP2ButtonPins);
#else
LadderInput p1_input(config::kP1LadderPin);
LadderInput p2_input(config::kP2LadderPin);
#endif

// --- Lamp hardware ----------------------------------------------------------
#if WAM_LIGHTS_PIXELS
// Both players share one chain; P1 owns it and transmits for both.
PixelLights p1_lights(0, true);
PixelLights p2_lights(config::kButtonsPerPlayer* config::kPixelsPerButton, false);
#else
DigitalLights p1_lights(config::kP1LedPins);
DigitalLights p2_lights(config::kP2LedPins);
#endif

Player p1("P1", p1_input, p1_lights);
Player p2("P2", p2_input, p2_lights);
Game game(p1, p2);

// These constructors only store references. Nothing touches a pin or a serial
// port until Game::Begin() runs below, because global constructors run before
// the core has finished initializing the hardware.

void setup() {
  game.Begin();
}

void loop() {
  static uint32_t last_tick_ms = 0;

  const uint32_t now_ms = millis();

  // Buttons are sampled every pass so a quick tap between ticks is not lost.
  // The old loop ended in delay(10), which capped input resolution at 10 ms and
  // would have blocked the audio library outright.
  game.PollInputs(now_ms);

  if (now_ms - last_tick_ms >= config::kTickIntervalMs) {
    last_tick_ms = now_ms;
    game.Tick(now_ms);
  }
}
