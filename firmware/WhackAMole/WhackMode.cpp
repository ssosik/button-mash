#include "Mode.h"

// The original game, moved here from Player with its behaviour unchanged: one
// cap blinks, hitting it scores by how quick you were, any other cap costs a
// penalty, and a mole nobody hits moves on once its points have decayed away.

void WhackMode::Begin(uint32_t now_ms) {
  _mole = -1;
  NewMole(now_ms);
}

void WhackMode::NewMole(uint32_t now_ms) {
  if (_mole >= 0) {
    Lamps().Set((uint8_t) _mole, colors::kOff);
  }

  // Never the same cap twice in a row. Without this a player can lean on one
  // button and keep scoring whenever random() repeats.
  int8_t next = _mole;
  while (next == _mole) {
    next = (int8_t) random(0, config::kButtonsPerPlayer);
  }
  _mole = next;

  Lamps().Set((uint8_t) _mole, colors::kMole);
  _lamp_on = true;
  _mole_started_ms = now_ms;
  _last_blink_ms = now_ms;

  // A press that landed while the previous mole was expiring must not be
  // credited against the new one.
  ClearPresses();
}

void WhackMode::Update(uint32_t now_ms) {
  if (now_ms - _last_blink_ms >= config::kLedBlinkMs) {
    _last_blink_ms = now_ms;
    _lamp_on = !_lamp_on;
    Lamps().Set((uint8_t) _mole, _lamp_on ? colors::kMole : colors::kOff);
  }

  // Snapshot the target before consuming presses, so a hit that spawns a new
  // mole cannot make a same-tick press on another cap look like a miss against
  // a mole that has not been shown yet.
  const int8_t target = _mole;
  bool scored = false;

  for (uint8_t i = 0; i < config::kButtonsPerPlayer; i++) {
    if (!TakePress(i)) {
      continue;
    }
    if ((int8_t) i == target && !scored) {
      scored = true;
      Owner().AddPoints(Decaying(config::kMoleStartingPoints, 0, _mole_started_ms, now_ms,
                                 config::kMoleLifetimeMs));
    } else {
      Owner().Penalize(config::kWrongButtonPenalty);
    }
  }

  // Hit, or nobody got there in time: either way the mole moves on.
  if (scored || now_ms - _mole_started_ms >= config::kMoleLifetimeMs) {
    NewMole(now_ms);
  }
}
