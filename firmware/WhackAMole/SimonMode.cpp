#include "Mode.h"

void SimonMode::Begin(uint32_t now_ms) {
  _length = 0;
  for (uint8_t i = 0; i < config::kSimonStartLength; i++) {
    Extend();
  }
  StartShow(now_ms);
}

// Add one random step. Never the cap just used: with a short dark gap between
// steps, the same cap twice in a row is easy to miscount.
void SimonMode::Extend() {
  if (_length >= config::kSimonMaxLength) {
    return;
  }
  const int8_t last = _length > 0 ? (int8_t) _sequence[_length - 1] : -1;
  int8_t cap = last;
  while (cap == last) {
    cap = (int8_t) random(config::kButtonsPerPlayer);
  }
  _sequence[_length++] = (uint8_t) cap;
}

void SimonMode::StartShow(uint32_t now_ms) {
  _phase = Phase::Show;
  _phase_ms = now_ms;
  _lit = -1;
  SetAll(colors::kOff);
}

void SimonMode::Update(uint32_t now_ms) {
  switch (_phase) {
  case Phase::Show:
    UpdateShow(now_ms);
    break;
  case Phase::Input:
    UpdateInput(now_ms);
    break;
  case Phase::Result:
    if (now_ms - _phase_ms >= config::kSimonResultMs) {
      StartShow(now_ms);
    }
    break;
  }
}

// Play the sequence: a dark lead-in, then each step lit in its cap's own colour
// with a dark gap after it. Presses are ignored here and thrown away on the way
// into the input phase, so jumping the gun costs nothing but the press.
void SimonMode::UpdateShow(uint32_t now_ms) {
  const uint32_t elapsed = now_ms - _phase_ms;
  int8_t lit = -1;

  if (elapsed >= config::kSimonLeadInMs) {
    const uint32_t slot_ms = config::kSimonOnMs + config::kSimonGapMs;
    const uint32_t into = elapsed - config::kSimonLeadInMs;
    const uint32_t slot = into / slot_ms;

    if (slot >= _length) {
      SetAll(colors::kOff);
      ClearPresses();
      _phase = Phase::Input;
      _phase_ms = now_ms;
      _last_press_ms = now_ms;
      _step = 0;
      _lit = -1;
      _echo = -1;
      return;
    }
    if (into % slot_ms < config::kSimonOnMs) {
      lit = (int8_t) _sequence[slot];
    }
  }

  if (lit != _lit) {
    if (_lit >= 0) {
      Lamps().Set((uint8_t) _lit, colors::kOff);
    }
    if (lit >= 0) {
      Lamps().Set((uint8_t) lit, colors::kCapColors[lit]);
    }
    _lit = lit;
  }
}

void SimonMode::UpdateInput(uint32_t now_ms) {
  if (_echo >= 0 && now_ms - _echo_ms >= config::kSimonEchoMs) {
    Lamps().Set((uint8_t) _echo, colors::kOff);
    _echo = -1;
  }

  for (uint8_t i = 0; i < config::kButtonsPerPlayer; i++) {
    if (!TakePress(i)) {
      continue;
    }

    // Light what was pressed, in its own colour, so the player sees the
    // sequence they played as well as feeling it.
    if (_echo >= 0) {
      Lamps().Set((uint8_t) _echo, colors::kOff);
    }
    _echo = (int8_t) i;
    _echo_ms = now_ms;
    Lamps().Set(i, colors::kCapColors[i]);
    _last_press_ms = now_ms;

    if (i != _sequence[_step]) {
      Owner().Penalize(config::kSimonMissPenalty);
      Finish(false, now_ms);
      return;
    }
    if (++_step == _length) {
      Owner().AddPoints(config::kSimonPointsPerStep * _length);
      Extend();
      Finish(true, now_ms);
      return;
    }
  }

  // Waiting it out is not a strategy: silence counts as a miss.
  if (now_ms - _last_press_ms >= config::kSimonInputTimeoutMs) {
    Owner().Penalize(config::kSimonMissPenalty);
    Finish(false, now_ms);
  }
}

// Every cap green for a pass, red for a miss, then the show runs again --
// one step longer after a pass, unchanged after a miss.
void SimonMode::Finish(bool passed, uint32_t now_ms) {
  SetAll(passed ? colors::kHit : colors::kMiss);
  _echo = -1;
  _phase = Phase::Result;
  _phase_ms = now_ms;
}
