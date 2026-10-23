#include "Mode.h"

void CaptchaMode::Begin(uint32_t now_ms) {
  _target_cap = -1;
  _target = (uint8_t) random(palette::kCount);
  _target_since_ms = now_ms;
  Deal(now_ms);
}

// Put a different palette colour on every cap, one of them the target. The
// target lands on a new cap each deal, never the one it just left, so the eye
// has to go and find it rather than stay put.
void CaptchaMode::Deal(uint32_t now_ms) {
  uint8_t pool[palette::kCount];
  for (uint8_t i = 0; i < palette::kCount; i++) {
    pool[i] = i;
  }
  for (uint8_t i = palette::kCount - 1; i > 0; i--) {
    const uint8_t j = (uint8_t) random(i + 1);
    const uint8_t held = pool[i];
    pool[i] = pool[j];
    pool[j] = held;
  }

  int8_t cap = _target_cap;
  while (cap == _target_cap) {
    cap = (int8_t) random(config::kButtonsPerPlayer);
  }

  // Hand the shuffled colours out in order, skipping the target, which only
  // ever goes on the chosen cap.
  uint8_t next = 0;
  for (uint8_t c = 0; c < config::kButtonsPerPlayer; c++) {
    uint8_t color = _target;
    if ((int8_t) c != cap) {
      while (pool[next] == _target) {
        next++;
      }
      color = pool[next++];
    }
    Lamps().Set(c, palette::kColors[color]);
  }

  _previous_cap = _target_cap;
  _target_cap = cap;
  _dealt_ms = now_ms;
}

void CaptchaMode::NewTarget(uint32_t now_ms) {
  uint8_t next = _target;
  while (next == _target) {
    next = (uint8_t) random(palette::kCount);
  }
  _target = next;
  _target_since_ms = now_ms;
  Deal(now_ms);
  // The old position showed the old colour. A late press there is a miss, not
  // a hit that arrived inside the grace window.
  _previous_cap = -1;
  ClearPresses();
}

void CaptchaMode::Update(uint32_t now_ms) {
  // A reaction already under way when the caps reshuffle still counts for a
  // moment. Without this the deal steals hits the player had earned.
  const bool in_grace = _previous_cap >= 0 && now_ms - _dealt_ms < config::kCaptchaGraceMs;
  bool found = false;

  for (uint8_t i = 0; i < config::kButtonsPerPlayer; i++) {
    if (!TakePress(i)) {
      continue;
    }
    const bool on_target =
        (int8_t) i == _target_cap || (in_grace && (int8_t) i == _previous_cap);
    if (on_target && !found) {
      found = true;
      Owner().AddPoints(Decaying(config::kCaptchaStartPoints, config::kCaptchaFloorPoints,
                                 _target_since_ms, now_ms, config::kCaptchaDecayMs));
    } else {
      Owner().Penalize(config::kCaptchaMissPenalty);
    }
  }

  if (found) {
    NewTarget(now_ms);
  } else if (now_ms - _dealt_ms >= config::kCaptchaShuffleMs) {
    Deal(now_ms);
  }
}
