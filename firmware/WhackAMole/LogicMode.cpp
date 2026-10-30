#include "Mode.h"

Color LogicMode::Target() const {
  return _target < config::kLogicColorCount ? palette::kColors[_target] : colors::kOff;
}

void LogicMode::Begin(uint32_t now_ms) {
  NewPuzzle(now_ms);
}

// A new target, and every cap started somewhere else, so each button needs at
// least one press and a board is never handed over already solved.
void LogicMode::NewPuzzle(uint32_t now_ms) {
  uint8_t target = _target;
  while (target == _target) {
    target = (uint8_t) random(config::kLogicColorCount);
  }
  _target = target;

  for (uint8_t c = 0; c < config::kButtonsPerPlayer; c++) {
    uint8_t level = _target;
    while (level == _target) {
      level = (uint8_t) random(config::kLogicColorCount);
    }
    _level[c] = level;
    Lamps().Set(c, palette::kColors[level]);
  }

  _puzzle_since_ms = now_ms;
  _solved = false;
  ClearPresses();
}

bool LogicMode::Solved() const {
  for (uint8_t c = 0; c < config::kButtonsPerPlayer; c++) {
    if (_level[c] != _target) {
      return false;
    }
  }
  return true;
}

void LogicMode::Update(uint32_t now_ms) {
  // Leave the matched board up for a moment -- seeing every cap agree is the
  // reward -- then deal the next one. NewPuzzle discards presses made meanwhile.
  if (_solved) {
    if (now_ms - _solved_ms >= config::kLogicSolvedHoldMs) {
      NewPuzzle(now_ms);
    }
    return;
  }

  bool pressed = false;
  for (uint8_t c = 0; c < config::kButtonsPerPlayer; c++) {
    if (!TakePress(c)) {
      continue;
    }
    _level[c] = (uint8_t) ((_level[c] + 1) % config::kLogicColorCount);
    Lamps().Set(c, palette::kColors[_level[c]]);
    pressed = true;
  }

  if (pressed && Solved()) {
    Owner().AddPoints(Decaying(config::kLogicStartPoints, config::kLogicFloorPoints,
                               _puzzle_since_ms, now_ms, config::kLogicDecayMs));
    _solved = true;
    _solved_ms = now_ms;
  }
}
