#include "Mode.h"

uint8_t ChaseMode::CapAt(uint8_t position) {
  return config::kChasePath[position % config::kButtonsPerPlayer];
}

void ChaseMode::Begin(uint32_t now_ms) {
  _position = (uint8_t) random(config::kButtonsPerPlayer);
  _step_ms = config::kChaseStartStepMs;
  _stepped_ms = now_ms;
  _hit_here = false;
  _hit_next = false;
  Draw();
}

void ChaseMode::Draw() {
  SetAll(colors::kChaseBackground);
  Lamps().Set(CapAt(_position), _hit_here ? colors::kHit : colors::kChaseRunner);
}

// Points and penalties both scale with the pace. A player who keeps the runner
// fast is paid for the risk -- but a fixed penalty against a growing reward made
// mashing profitable: once a lucky streak sped the runner up, each lucky hit
// paid more than each miss cost. Scaling both keeps mashing a loss at any speed.
int ChaseMode::AtPace(int points) const {
  return (int) (((int32_t) points * config::kChaseStartStepMs) / _step_ms);
}

// Score at the current pace, then speed up.
void ChaseMode::Hit() {
  Owner().AddPoints(AtPace(config::kChaseHitPoints));
  const uint32_t faster = _step_ms * config::kChaseSpeedupPct / 100;
  _step_ms = faster < config::kChaseMinStepMs ? config::kChaseMinStepMs : faster;
}

void ChaseMode::Update(uint32_t now_ms) {
  const uint8_t here = CapAt(_position);
  const uint8_t next = CapAt(_position + 1);
  // The anticipating press: the next cap, just before the runner lands on it.
  const bool early = now_ms - _stepped_ms + config::kChaseEarlyMs >= _step_ms;
  bool redraw = false;

  for (uint8_t i = 0; i < config::kButtonsPerPlayer; i++) {
    if (!TakePress(i)) {
      continue;
    }
    if (i == here && !_hit_here) {
      _hit_here = true;
      Hit();
      redraw = true;
    } else if (i == next && early && !_hit_next) {
      _hit_next = true; // credited now; it turns green when the runner arrives
      Hit();
    } else if ((i == here && _hit_here) || (i == next && _hit_next)) {
      // The right cap, pressed again on the same visit. No second score, but
      // no penalty either: it was not a wrong button.
    } else {
      Owner().Penalize(AtPace(config::kChaseMissPenalty));
    }
  }

  if (now_ms - _stepped_ms >= _step_ms) {
    // A visit that ends unhit eases the pace back toward the start, so a player
    // who falls behind is not left facing top speed for the rest of the segment.
    if (!_hit_here) {
      const uint32_t slower = _step_ms * config::kChaseSlowdownPct / 100;
      _step_ms = slower > config::kChaseStartStepMs ? config::kChaseStartStepMs : slower;
    }
    _position = (uint8_t) ((_position + 1) % config::kButtonsPerPlayer);
    _stepped_ms = now_ms;
    _hit_here = _hit_next;
    _hit_next = false;
    redraw = true;
  }

  if (redraw) {
    Draw();
  }
}
