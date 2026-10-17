#include "Mode.h"

namespace {

const char* const kBanners[kModeCount] = {
#define X(id, cls, member, banner, ms) banner,
    MODE_LIST(X)
#undef X
};

constexpr uint32_t kLengthsMs[kModeCount] = {
#define X(id, cls, member, banner, ms) ms,
    MODE_LIST(X)
#undef X
};

// kChasePath is edited by hand to match the table, so make sure it is a real
// ring. A repeated or missing index would give a cap the runner never visits,
// or visits twice a lap, and that is much easier to catch here than by eye.
constexpr bool ChasePathIsRing() {
  bool seen[config::kButtonsPerPlayer] = {};
  for (uint8_t i = 0; i < config::kButtonsPerPlayer; i++) {
    const uint8_t cap = config::kChasePath[i];
    if (cap >= config::kButtonsPerPlayer || seen[cap]) {
      return false;
    }
    seen[cap] = true;
  }
  return true;
}
static_assert(ChasePathIsRing(), "config::kChasePath must list every cap exactly once");

} // namespace

const char* ModeBanner(ModeId id) {
  return (uint8_t) id < kModeCount ? kBanners[(uint8_t) id] : "";
}

uint32_t ModeLengthMs(ModeId id) {
  return (uint8_t) id < kModeCount ? kLengthsMs[(uint8_t) id] : 0;
}

void Mode::SetAll(Color color) {
  for (uint8_t i = 0; i < config::kButtonsPerPlayer; i++) {
    Lamps().Set(i, color);
  }
}

int Mode::Decaying(int start, int floor, uint32_t since_ms, uint32_t now_ms, uint32_t window_ms) {
  const uint32_t elapsed = now_ms - since_ms;
  if (window_ms == 0 || elapsed >= window_ms) {
    return floor;
  }
  const int64_t span = (int64_t) start - floor;
  return start - (int) ((span * elapsed) / window_ms);
}

PlayerModes::PlayerModes(Player& owner)
    :
#define X(id, cls, member, banner, ms) member(owner),
      MODE_LIST(X)
#undef X
          _end(0) {
}

Mode& PlayerModes::Get(ModeId id) {
  switch (id) {
#define X(id_, cls, member, banner, ms)                                                            \
  case ModeId::id_:                                                                                \
    return member;
    MODE_LIST(X)
#undef X
  case ModeId::Count:
    break;
  }
  return whack; // unreachable for any real id, but every path has to return
}
