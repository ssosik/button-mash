#include "Dance.h"

namespace {

// Saturated colours only. White would wash the spin out to one blur, and the
// dance should look nothing like the plain white the table powers on in.
constexpr Color kDanceColors[] = {colors::kRed, colors::kYellow, colors::kGreen, colors::kBlue,
                                  colors::kMagenta};
constexpr uint8_t kDanceColorCount = sizeof(kDanceColors) / sizeof(kDanceColors[0]);

enum class Pattern : uint8_t { Spin, Flash, Alternate, Count };

} // namespace

void Dance(Lights& lamps, uint32_t elapsed_ms, bool reverse) {
  const uint32_t step = elapsed_ms / config::kDanceStepMs;
  const Pattern pattern =
      (Pattern) ((elapsed_ms / config::kDancePatternMs) % (uint32_t) Pattern::Count);
  const uint8_t n = config::kButtonsPerPlayer;

  for (uint8_t position = 0; position < n; position++) {
    // Where this cap sits around the ring, counted the way this player spins.
    const uint8_t place = reverse ? (uint8_t) ((n - position) % n) : position;
    Color color = colors::kOff;

    switch (pattern) {
    case Pattern::Spin:
      color = kDanceColors[(place + n * kDanceColorCount - step % (n * kDanceColorCount)) %
                           kDanceColorCount];
      break;
    case Pattern::Flash:
      if (step % 2 == 0) {
        color = kDanceColors[(step / 2) % kDanceColorCount];
      }
      break;
    case Pattern::Alternate:
      // An odd ring cannot alternate evenly, so one pair of neighbours always
      // matches -- it reads as the pattern turning, which suits a dance.
      if ((place + step) % 2 == 0) {
        color = kDanceColors[(step / 2) % kDanceColorCount];
      }
      break;
    case Pattern::Count:
      break;
    }

    lamps.Set(config::kChasePath[position], color);
  }
}
