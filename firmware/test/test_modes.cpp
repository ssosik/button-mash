// Host-side tests for the game modes. Run with `make test`.
//
// Each mode is played by a scripted player who sees only what a real one would
// -- the cap colours, and the target the display shows -- and presses buttons
// through the real ButtonInput, so the debounce and press latch are the ones
// the table runs. The checks are the promises each mode makes to a player.

#include "Arduino.h"
#include "ButtonInput.h"
#include "Config.h"
#include "Dance.h"
#include "Lights.h"
#include "Mode.h"
#include "Player.h"

#include <algorithm>
#include <cstdio>
#include <cstring>
#include <functional>
#include <vector>

// --- Deterministic random() -------------------------------------------------

namespace {
uint64_t g_rng = 1;
} // namespace

long random(long howbig) {
  if (howbig <= 0) {
    return 0;
  }
  g_rng = g_rng * 6364136223846793005ULL + 1442695040888963407ULL;
  return (long) ((g_rng >> 33) % (uint64_t) howbig);
}

long random(long howsmall, long howbig) {
  return howbig <= howsmall ? howsmall : howsmall + random(howbig - howsmall);
}

void randomSeed(unsigned long seed) {
  g_rng = seed ? seed : 1;
}

namespace {

constexpr uint8_t kCaps = config::kButtonsPerPlayer;

// --- Fakes ------------------------------------------------------------------

class FakeInput : public ButtonInput {
public:
  void Begin() override {}
  bool raw[config::kInputsPerPlayer] = {};

protected:
  void ReadRaw(bool out[config::kInputsPerPlayer]) override {
    for (uint8_t i = 0; i < config::kInputsPerPlayer; i++) {
      out[i] = raw[i];
    }
  }
};

class FakeLights : public Lights {
public:
  void Begin() override {}
  void Set(uint8_t index, Color color) override {
    if (index < kCaps) {
      cap[index] = color;
    }
  }
  void Show() override {}
  Color cap[kCaps] = {};
};

// --- Harness ----------------------------------------------------------------

int g_checks = 0;
int g_failures = 0;

#define CHECK(cond, ...)                                                                           \
  do {                                                                                             \
    g_checks++;                                                                                    \
    if (!(cond)) {                                                                                 \
      g_failures++;                                                                                \
      std::printf("    FAIL (line %d): ", __LINE__);                                               \
      std::printf(__VA_ARGS__);                                                                    \
      std::printf("\n");                                                                           \
    }                                                                                              \
  } while (0)

// One player at the table. Time starts away from zero, as millis() would.
struct Rig {
  FakeInput input;
  FakeLights lights;
  Player player{"T", input, lights};
  uint32_t now = 1000;
  uint32_t release_at[config::kInputsPerPlayer] = {};
  uint32_t free_at = 0;
  int presses = 0;

  // A finger needs to come off and stay off past the debounce before the same
  // hand can make another press register; a scripted one is held to that too.
  bool CanPress() const { return now >= free_at; }

  // Held 40 ms: comfortably past the 25 ms debounce, like a real press.
  void Press(uint8_t i) {
    input.raw[i] = true;
    release_at[i] = now + 40;
    free_at = now + 40 + config::kDebounceMs + 5;
    presses++;
  }

  // Advance `ms`, polling every millisecond as loop() does and running the mode
  // every tick, then letting the player look at the result.
  void Run(Mode& mode, uint32_t ms, const std::function<void()>& each_tick) {
    for (uint32_t t = 0; t < ms; t++) {
      now++;
      for (uint8_t i = 0; i < config::kInputsPerPlayer; i++) {
        if (input.raw[i] && now >= release_at[i]) {
          input.raw[i] = false;
        }
      }
      input.Poll(now);
      if (now % config::kTickIntervalMs == 0) {
        mode.Update(now);
        if (each_tick) {
          each_tick();
        }
      }
    }
  }
};

int CountColor(const FakeLights& l, Color c) {
  int n = 0;
  for (uint8_t i = 0; i < kCaps; i++) {
    n += l.cap[i] == c;
  }
  return n;
}

int FindColor(const FakeLights& l, Color c) {
  for (uint8_t i = 0; i < kCaps; i++) {
    if (l.cap[i] == c) {
      return i;
    }
  }
  return -1;
}

bool AllColor(const FakeLights& l, Color c) {
  return CountColor(l, c) == kCaps;
}

bool InPalette(Color c) {
  for (uint8_t i = 0; i < palette::kCount; i++) {
    if (palette::kColors[i] == c) {
      return true;
    }
  }
  return false;
}

// Chase: the one cap that is not the background, or -1.
int Runner(const FakeLights& l) {
  int at = -1;
  int count = 0;
  for (uint8_t i = 0; i < kCaps; i++) {
    if (l.cap[i] != colors::kChaseBackground) {
      at = i;
      count++;
    }
  }
  return count == 1 ? at : -1;
}

uint8_t PathNext(int cap) {
  for (uint8_t i = 0; i < kCaps; i++) {
    if (config::kChasePath[i] == cap) {
      return config::kChasePath[(i + 1) % kCaps];
    }
  }
  return 0xFF;
}

// --- Tests ------------------------------------------------------------------

void TestModeTable() {
  std::printf("mode table\n");
  FakeInput input;
  FakeLights lights;
  Player player("T", input, lights);
  PlayerModes modes(player);

  uint32_t total_ms = 0;
  for (uint8_t i = 0; i < kModeCount; i++) {
    const ModeId id = (ModeId) i;
    const char* banner = ModeBanner(id);
    CHECK(std::strlen(banner) >= 1 && std::strlen(banner) <= 5,
          "banner \"%s\" must be 1-5 characters to fit on the panel unscrolled", banner);
    CHECK(ModeLengthMs(id) > 0, "mode %u has no segment length", i);
    total_ms += ModeLengthMs(id);
    for (uint8_t j = 0; j < i; j++) {
      CHECK(&modes.Get(id) != &modes.Get((ModeId) j), "modes %u and %u share one instance", i, j);
    }
  }
  std::printf("    %u modes, %.1f s of play plus %.1f s of banners\n", kModeCount,
              total_ms / 1000.0, kModeCount * config::kModeIntroMs / 1000.0);
}

void TestWhack() {
  std::printf("whack\n");
  randomSeed(11);
  Rig r;
  WhackMode mode(r.player);
  mode.Begin(r.now);

  int last = 0;
  bool fell = false;
  bool two_moles = false;
  r.Run(mode, 12000, [&] {
    two_moles |= CountColor(r.lights, colors::kMole) > 1;
    fell |= r.player.Score() < last;
    last = r.player.Score();
    const int mole = FindColor(r.lights, colors::kMole);
    if (mole >= 0 && r.CanPress()) {
      r.Press((uint8_t) mole);
    }
  });
  CHECK(!two_moles, "more than one mole lit at once");
  CHECK(!fell, "a player who only ever hits the mole lost points");
  CHECK(r.player.Score() > 5000, "a perfect player scored only %d", r.player.Score());
  std::printf("    scripted perfect player: %d\n", r.player.Score());

  Rig w;
  WhackMode wrong(w.player);
  wrong.Begin(w.now);
  w.player.AddPoints(5000);
  const int mole = FindColor(w.lights, colors::kMole);
  w.Press((uint8_t) ((mole + 1) % kCaps));
  w.Run(wrong, 60, nullptr);
  CHECK(w.player.Score() == 5000 - config::kWrongButtonPenalty,
        "a wrong cap should cost %d, score is %d", config::kWrongButtonPenalty, w.player.Score());
}

void TestCaptcha() {
  std::printf("captcha\n");
  randomSeed(22);
  Rig r;
  CaptchaMode mode(r.player);
  mode.Begin(r.now);

  bool one_target = true;
  bool distinct = true;
  bool from_palette = true;
  auto check_board = [&] {
    one_target &= CountColor(r.lights, mode.Target()) == 1;
    for (uint8_t a = 0; a < kCaps; a++) {
      from_palette &= InPalette(r.lights.cap[a]);
      for (uint8_t b = 0; b < a; b++) {
        distinct &= r.lights.cap[a] != r.lights.cap[b];
      }
    }
  };
  check_board();

  int last = 0;
  int finds = 0;
  bool fell = false;
  Color target = mode.Target();
  r.Run(mode, 15000, [&] {
    check_board();
    fell |= r.player.Score() < last;
    last = r.player.Score();
    if (mode.Target() != target) {
      finds++;
      target = mode.Target();
    }
    const int cap = FindColor(r.lights, mode.Target());
    if (cap >= 0 && r.CanPress()) {
      r.Press((uint8_t) cap);
    }
  });
  CHECK(one_target, "the target colour was not on exactly one cap at some point");
  CHECK(distinct, "two caps showed the same colour");
  CHECK(from_palette, "a cap showed a colour outside the palette");
  // A press already on its way when the caps reshuffle lands on the old cap.
  // The grace window is what keeps that from costing a perfect player points.
  CHECK(!fell, "a player who only ever presses the target lost points");
  CHECK(finds >= 10, "only %d finds in a segment", finds);
  std::printf("    scripted perfect player: %d from %d finds\n", r.player.Score(), finds);

  // The grace window, directly: press where the target was, just after a deal.
  randomSeed(23);
  Rig g;
  CaptchaMode grace(g.player);
  grace.Begin(g.now);
  const Color asked = grace.Target();
  int where = FindColor(g.lights, asked);
  bool pressed_old = false;
  g.Run(grace, config::kCaptchaShuffleMs + 100, [&] {
    const int now_at = FindColor(g.lights, asked);
    if (!pressed_old && grace.Target() == asked && now_at != where) {
      g.Press((uint8_t) where);
      pressed_old = true;
    }
    where = now_at;
  });
  CHECK(pressed_old, "the caps never reshuffled");
  CHECK(g.player.Score() > 0, "a press on the old cap inside the grace window was not credited");

  Rig w;
  CaptchaMode wrong(w.player);
  wrong.Begin(w.now);
  w.player.AddPoints(5000);
  const int cap = FindColor(w.lights, wrong.Target());
  w.Press((uint8_t) ((cap + 1) % kCaps));
  w.Run(wrong, 60, nullptr);
  CHECK(w.player.Score() == 5000 - config::kCaptchaMissPenalty,
        "a wrong cap should cost %d, score is %d", config::kCaptchaMissPenalty, w.player.Score());
}

void TestChase() {
  std::printf("chase\n");
  randomSeed(33);
  Rig r;
  ChaseMode mode(r.player);
  mode.Begin(r.now);

  bool one_runner = true;
  bool in_order = true;
  bool fell = false;
  int last = 0;
  int at = Runner(r.lights);
  uint32_t arrived = r.now;
  std::vector<uint32_t> dwell;

  r.Run(mode, 12000, [&] {
    const int runner = Runner(r.lights);
    if (runner < 0) {
      one_runner = false;
      return;
    }
    if (runner != at) {
      in_order &= runner == PathNext(at);
      dwell.push_back(r.now - arrived);
      arrived = r.now;
      at = runner;
    }
    fell |= r.player.Score() < last;
    last = r.player.Score();
    if (r.lights.cap[runner] == colors::kChaseRunner && r.CanPress()) {
      r.Press((uint8_t) runner);
    }
  });
  CHECK(one_runner, "the board did not always show exactly one runner");
  CHECK(in_order, "the runner skipped a cap or went the wrong way round kChasePath");
  CHECK(!fell, "a player who only ever hits the runner lost points");
  CHECK(dwell.size() > 10 && dwell.front() > dwell.back(), "the runner did not speed up with hits");
  CHECK(!dwell.empty() && dwell.back() <= config::kChaseMinStepMs + config::kTickIntervalMs,
        "after a run of hits the runner should reach its top speed, dwell is %u ms",
        dwell.empty() ? 0 : dwell.back());
  std::printf("    scripted perfect player: %d, dwell %u ms falling to %u ms\n", r.player.Score(),
              dwell.empty() ? 0 : dwell.front(), dwell.empty() ? 0 : dwell.back());

  // Anticipation: the next cap, pressed just before the runner lands, scores.
  randomSeed(34);
  Rig e;
  ChaseMode early(e.player);
  early.Begin(e.now);
  const uint8_t next = PathNext(Runner(e.lights));
  e.Run(early, config::kChaseStartStepMs - config::kChaseEarlyMs / 2 - 35, nullptr);
  e.Press(next);
  e.Run(early, 40, nullptr);
  const int credited = e.player.Score();
  e.Run(early, config::kChaseEarlyMs, nullptr);
  CHECK(credited > 0, "a press on the next cap just before the runner landed was not credited");
  CHECK(e.lights.cap[next] == colors::kHit, "a cap credited early is not green once it arrives");

  Rig w;
  ChaseMode wrong(w.player);
  wrong.Begin(w.now);
  w.player.AddPoints(5000);
  const int here = Runner(w.lights);
  uint8_t elsewhere = 0;
  while (elsewhere == here || elsewhere == PathNext(here)) {
    elsewhere++;
  }
  w.Press(elsewhere);
  w.Run(wrong, 60, nullptr);
  CHECK(w.player.Score() == 5000 - config::kChaseMissPenalty,
        "a wrong cap should cost %d, score is %d", config::kChaseMissPenalty, w.player.Score());
}

void TestLogic() {
  std::printf("logic\n");
  randomSeed(44);
  Rig r;
  LogicMode mode(r.player);
  mode.Begin(r.now);

  bool fresh = true;
  auto check_fresh = [&] { fresh &= CountColor(r.lights, mode.Target()) == 0; };
  check_fresh();

  Color target = mode.Target();
  int solved = 0;
  int presses = 0;
  int fewest = 99;
  int most = 0;
  int last = 0;
  bool fell = false;
  r.Run(mode, 20000, [&] {
    if (mode.Target() != target) {
      check_fresh();
      target = mode.Target();
    }
    if (r.player.Score() > last) {
      solved++;
      fewest = std::min(fewest, presses);
      most = std::max(most, presses);
      presses = 0;
    }
    fell |= r.player.Score() < last;
    last = r.player.Score();
    if (!r.CanPress()) {
      return;
    }
    for (uint8_t c = 0; c < kCaps; c++) {
      if (r.lights.cap[c] != mode.Target()) {
        r.Press(c);
        presses++;
        break;
      }
    }
  });
  CHECK(fresh, "a puzzle was dealt with a cap already showing the target");
  CHECK(!fell, "solving lost points");
  CHECK(solved >= 3, "only %d puzzles solved in a segment", solved);
  CHECK(fewest >= kCaps, "a puzzle was solved in %d presses; every cap should need one", fewest);
  CHECK(most <= kCaps * (config::kLogicColorCount - 1), "a puzzle needed %d presses", most);
  std::printf("    scripted perfect player: %d from %d puzzles, %d-%d presses each\n",
              r.player.Score(), solved, fewest, most);
}

void TestSimon() {
  std::printf("simon\n");
  randomSeed(55);
  Rig r;
  SimonMode mode(r.player);
  mode.Begin(r.now);

  // A player who watches: records each step as it lights, replays once the
  // show has gone quiet, and reads the green or red flash that follows.
  enum class Watch { Recording, Replaying, Result };
  Watch watch = Watch::Recording;
  std::vector<uint8_t> seen;
  std::vector<std::vector<uint8_t>> shows;
  std::vector<bool> passed;
  int last_lit = -1;
  uint32_t dark_since = r.now;
  size_t replayed = 0;
  bool own_colours = true;
  bool answered_wrong = false;

  r.Run(mode, 30000, [&] {
    int lit = -1;
    int count = 0;
    for (uint8_t c = 0; c < kCaps; c++) {
      if (!r.lights.cap[c].IsOff()) {
        lit = c;
        count++;
      }
    }

    const bool pass = AllColor(r.lights, colors::kHit);
    const bool fail = AllColor(r.lights, colors::kMiss);
    if ((pass || fail) && watch != Watch::Result) {
      passed.push_back(pass);
      watch = Watch::Result;
      return;
    }

    switch (watch) {
    case Watch::Result:
      if (count == 0) {
        watch = Watch::Recording;
        seen.clear();
        last_lit = -1;
        dark_since = r.now;
      }
      break;

    case Watch::Recording:
      if (count == 1 && lit != last_lit) {
        own_colours &= r.lights.cap[lit] == colors::kCapColors[lit];
        seen.push_back((uint8_t) lit);
      }
      if (count == 0 && last_lit >= 0) {
        dark_since = r.now;
      }
      last_lit = count == 1 ? lit : -1;
      if (!seen.empty() && count == 0 && r.now - dark_since > config::kSimonGapMs + 60) {
        shows.push_back(seen);
        watch = Watch::Replaying;
        replayed = 0;
      }
      break;

    case Watch::Replaying:
      if (replayed < seen.size() && r.CanPress()) {
        uint8_t cap = seen[replayed];
        // Once, after two passes, get the first step wrong on purpose.
        if (!answered_wrong && passed.size() == 2 && replayed == 0) {
          cap = (uint8_t) ((cap + 1) % kCaps);
          answered_wrong = true;
        }
        r.Press(cap);
        replayed++;
      }
      break;
    }
  });

  CHECK(own_colours, "a step was not lit in its cap's own colour");
  CHECK(shows.size() >= 5, "only %zu rounds played", shows.size());
  CHECK(!shows.empty() && shows[0].size() == config::kSimonStartLength,
        "the first sequence should be %u long", config::kSimonStartLength);

  int passes = 0;
  bool grew = true;
  bool replayed_same = true;
  bool saw_fail = false;
  for (size_t i = 0; i + 1 < shows.size() && i < passed.size(); i++) {
    const auto& a = shows[i];
    const auto& b = shows[i + 1];
    if (passed[i]) {
      passes++;
      // Classic Simon: the same sequence again, one step longer.
      grew &= b.size() == a.size() + 1 && std::equal(a.begin(), a.end(), b.begin());
    } else {
      saw_fail = true;
      replayed_same &= a == b;
    }
  }
  CHECK(grew, "a pass did not replay the same sequence one step longer");
  CHECK(saw_fail, "the deliberate wrong answer did not fail the round");
  CHECK(replayed_same, "a failed round did not replay the same sequence");
  std::printf("    scripted player: %d, %d passes, sequence reached %zu\n", r.player.Score(),
              passes, shows.empty() ? 0 : shows.back().size());

  // Silence is a miss, not a way to wait out the segment.
  randomSeed(56);
  Rig s;
  SimonMode silent(s.player);
  silent.Begin(s.now);
  s.player.AddPoints(5000);
  bool red = false;
  s.Run(silent, 9000, [&] { red |= AllColor(s.lights, colors::kMiss); });
  CHECK(red, "a player who never presses was never shown a miss");
  CHECK(s.player.Score() < 5000, "a player who never presses was never penalized");
}

// Every mode, mashed at random. Two things must hold. Nothing goes out of range
// -- built with the sanitizers, a bad cap index fails here instead of scribbling
// over memory on the Teensy. And mashing must not pay.
//
// The score starts from a large bank so the floor at zero never engages. Without
// it the floor alone ratchets a random walk upward -- losses stop at zero and
// gains do not -- and every mode looks as though mashing works.
void TestMasher() {
  std::printf("masher, every mode (from a bank of 1,000,000)\n");
  constexpr int kBank = 1000000;
  for (uint8_t i = 0; i < kModeCount; i++) {
    const ModeId id = (ModeId) i;
    randomSeed(100 + i);
    Rig r;
    PlayerModes modes(r.player);
    Mode& mode = modes.Get(id);
    r.player.AddPoints(kBank);
    mode.Begin(r.now);
    r.Run(mode, ModeLengthMs(id), [&] {
      if (r.CanPress()) {
        r.Press((uint8_t) random(kCaps));
      }
    });
    const int gain = r.player.Score() - kBank;
    if (id == ModeId::Logic) {
      // Logic has no wrong button -- every press is a move -- so mashing can't
      // be made to cost anything. It only has to be useless: a random walk over
      // 4^5 boards rarely lands on a solution inside one segment.
      CHECK(gain <= 2 * config::kLogicStartPoints, "LOGIC: mashing earned %d", gain);
    } else {
      CHECK(gain < 0, "%s: mashing gained %d points", ModeBanner(id), gain);
    }
    std::printf("    %-5s %+7d from %d random presses\n", ModeBanner(id), gain, r.presses);
  }
}

void TestDance() {
  std::printf("dance\n");
  const Color dance[] = {colors::kRed, colors::kYellow, colors::kGreen, colors::kBlue,
                         colors::kMagenta};
  auto is_dance = [&](Color c) {
    for (const Color& d : dance) {
      if (c == d) {
        return true;
      }
    }
    return c.IsOff();
  };
  // Colour on the cap at ring position k (kChasePath order).
  auto at = [](const FakeLights& l, int k) {
    return l.cap[config::kChasePath[(k + kCaps) % kCaps]];
  };

  FakeLights fwd;
  FakeLights rev;
  FakeLights fwd_next;
  FakeLights rev_next;
  bool known = true;
  bool spins = true;
  bool mirrored = true;
  bool flashes = true;
  bool alternates = true;
  int lit_steps = 0;
  int steps = 0;
  const uint32_t step = config::kDanceStepMs;
  const uint32_t patterns = 3;

  for (uint32_t t = 0; t < patterns * config::kDancePatternMs * 2; t += step) {
    Dance(fwd, t, false);
    Dance(rev, t, true);
    Dance(fwd_next, t + step, false);
    Dance(rev_next, t + step, true);
    const uint32_t pattern = (t / config::kDancePatternMs) % patterns;
    const bool same_pattern = (t + step) / config::kDancePatternMs == t / config::kDancePatternMs;

    int lit = 0;
    int distinct_lit = 0;
    for (int k = 0; k < kCaps; k++) {
      known &= is_dance(fwd.cap[k]) && is_dance(rev.cap[k]);
      lit += !fwd.cap[k].IsOff();
      distinct_lit += !at(fwd, k).IsOff() && at(fwd, k) != at(fwd, k - 1);
    }
    lit_steps += lit > 0;
    steps++;

    if (pattern == 0 && same_pattern) {
      for (int k = 0; k < kCaps; k++) {
        // Each colour moves one place on: forward for P1, backward for P2.
        spins &= at(fwd_next, k + 1) == at(fwd, k);
        mirrored &= at(rev_next, k - 1) == at(rev, k);
      }
      spins &= distinct_lit == kCaps;
    }
    if (pattern == 1) {
      flashes &= lit == 0 || lit == kCaps;
    }
    if (pattern == 2) {
      // Never all on, never all off: it is the half-and-half swap.
      alternates &= lit > 0 && lit < kCaps;
    }
  }

  CHECK(known, "the dance showed a colour outside its set");
  CHECK(spins, "the spin did not carry every colour one place round the ring per step");
  CHECK(mirrored, "P2's spin does not run the opposite way to P1's");
  CHECK(flashes, "the flash lit some caps but not others");
  CHECK(alternates, "the alternate pattern lit all caps or none");
  CHECK(lit_steps * 4 >= steps * 3, "caps lit on only %d of %d steps", lit_steps, steps);
  std::printf("    caps lit on %d of %d steps\n", lit_steps, steps);
}

} // namespace

int main() {
  TestModeTable();
  TestWhack();
  TestCaptcha();
  TestChase();
  TestLogic();
  TestSimon();
  TestMasher();
  TestDance();
  std::printf("\n%d checks, %d failed\n", g_checks, g_failures);
  return g_failures == 0 ? 0 : 1;
}
