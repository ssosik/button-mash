#ifndef Mode_h
#define Mode_h

#include "Config.h"
#include "Lights.h"
#include "Player.h"
#include <Arduino.h>

// ---------------------------------------------------------------------------
// The ways to play, and the order a game runs through them.
//
// A game is a medley: each mode below runs for its own segment, both players at
// once, and score carries across the lot. Each player owns one instance of
// every mode (PlayerModes), so a mode's state is always exactly one player's
// board and the two can never end up sharing one.
//
// Modes set lamp colours but never call Show(). Game flushes once per tick,
// after both players have updated, so both players' changes reach the shared
// pixel chain in the same frame and in a single transfer.
//
//     X(id, class, member, banner, segment length in ms)
//
// The banner is drawn unscrolled between segments, like READY / SET / GO, so it
// must fit in five characters. The host tests enforce that.
// ---------------------------------------------------------------------------
#define MODE_LIST(X)                                                                               \
  X(Whack, WhackMode, whack, "WHACK", 12000)                                                       \
  X(Captcha, CaptchaMode, captcha, "FIND", 15000)                                                  \
  X(Chase, ChaseMode, chase, "CHASE", 12000)                                                       \
  X(Logic, LogicMode, logic, "LOGIC", 20000)                                                       \
  X(Simon, SimonMode, simon, "SIMON", 20000)

enum class ModeId : uint8_t {
#define X(id, cls, member, banner, ms) id,
  MODE_LIST(X)
#undef X
      Count
};

constexpr uint8_t kModeCount = (uint8_t) ModeId::Count;

const char* ModeBanner(ModeId id);
uint32_t ModeLengthMs(ModeId id);

// Colours a mode may ask a player to find. Six, so Captcha can deal a distinct
// colour to every cap and still leave one out, which keeps the deal from
// looking the same every time; Logic uses the first kLogicColorCount. Picked to
// stay distinct through tinted domes at kPixelBrightness -- tune them on the
// table, not here.
namespace palette {
constexpr Color kColors[] = {colors::kRed,    colors::kGreen,   colors::kBlue,
                             colors::kYellow, colors::kMagenta, colors::kWhite};
constexpr uint8_t kCount = sizeof(kColors) / sizeof(kColors[0]);

static_assert(kCount >= config::kButtonsPerPlayer, "Captcha deals a distinct colour to every cap");
static_assert(config::kLogicColorCount >= 2 && config::kLogicColorCount <= kCount,
              "Logic cycles through at least two palette colours");
} // namespace palette

class Mode {
public:
  virtual ~Mode() = default;

  // Start a segment. The lamps are already dark and stale presses discarded.
  virtual void Begin(uint32_t now_ms) = 0;

  // One tick: read presses, set lamps, award points.
  virtual void Update(uint32_t now_ms) = 0;

  // The colour the display should ask this player for, or colors::kOff when
  // the mode has no target.
  virtual Color Target() const { return colors::kOff; }

protected:
  explicit Mode(Player& owner) : _owner(&owner) {}

  Player& Owner() { return *_owner; }
  Lights& Lamps() { return _owner->Lamps(); }
  bool TakePress(uint8_t index) { return _owner->Input().TakePress(index); }
  void ClearPresses() { _owner->Input().ClearPresses(); }

  // Stage every cap. Unlike Lights::SetAll this does not flush; see above.
  void SetAll(Color color);

  // Points for an action begun at since_ms: `start` if instant, falling
  // linearly to `floor` across window_ms. Every timed mode scores through this
  // so their numbers stay comparable across a medley.
  static int Decaying(int start, int floor, uint32_t since_ms, uint32_t now_ms,
                      uint32_t window_ms);

private:
  Player* _owner;
};

// --- Whack: the original game ----------------------------------------------
//
// One cap blinks. Hit it before it moves on; the sooner, the more it is worth.
class WhackMode : public Mode {
public:
  explicit WhackMode(Player& owner) : Mode(owner) {}
  void Begin(uint32_t now_ms) override;
  void Update(uint32_t now_ms) override;

private:
  void NewMole(uint32_t now_ms);

  int8_t _mole = -1;
  uint32_t _mole_started_ms = 0;
  uint32_t _last_blink_ms = 0;
  bool _lamp_on = false;
};

// --- Captcha ---------------------------------------------------------------
//
// The display names a colour. Every cap shows a different colour, reshuffling
// on a timer; press the cap that is showing the named one.
class CaptchaMode : public Mode {
public:
  explicit CaptchaMode(Player& owner) : Mode(owner) {}
  void Begin(uint32_t now_ms) override;
  void Update(uint32_t now_ms) override;
  Color Target() const override { return palette::kColors[_target]; }

private:
  void NewTarget(uint32_t now_ms);
  void Deal(uint32_t now_ms);

  uint8_t _target = 0;       // palette index being asked for
  int8_t _target_cap = -1;   // the cap showing it
  int8_t _previous_cap = -1; // where it was before the last deal; see kCaptchaGraceMs
  uint32_t _target_since_ms = 0;
  uint32_t _dealt_ms = 0;
};

// --- Chase -----------------------------------------------------------------
//
// Every cap a dim white; one coloured runner steps around the ring. Hit the cap
// it is on -- or the next one, just before it lands.
class ChaseMode : public Mode {
public:
  explicit ChaseMode(Player& owner) : Mode(owner) {}
  void Begin(uint32_t now_ms) override;
  void Update(uint32_t now_ms) override;

private:
  static uint8_t CapAt(uint8_t position);
  int AtPace(int points) const;
  void Hit();
  void Draw();

  uint8_t _position = 0;    // index into config::kChasePath
  uint32_t _step_ms = 0;    // the runner's current dwell per cap
  uint32_t _stepped_ms = 0; // when it arrived where it is
  bool _hit_here = false;   // this visit has scored
  bool _hit_next = false;   // the next visit already scored, by an early press
};

// --- Logic -----------------------------------------------------------------
//
// Each press steps a cap to its next colour. Get all five showing the colour
// named on the display.
class LogicMode : public Mode {
public:
  explicit LogicMode(Player& owner) : Mode(owner) {}
  void Begin(uint32_t now_ms) override;
  void Update(uint32_t now_ms) override;
  Color Target() const override;

private:
  void NewPuzzle(uint32_t now_ms);
  bool Solved() const;

  uint8_t _level[config::kButtonsPerPlayer] = {}; // palette index each cap shows
  uint8_t _target = config::kLogicColorCount;     // out of range until the first puzzle
  uint32_t _puzzle_since_ms = 0;
  uint32_t _solved_ms = 0;
  bool _solved = false;
};

// --- Simon -----------------------------------------------------------------
//
// Watch the sequence, then play it back. Right, and it grows by one; wrong, or
// too slow, and the same sequence plays again.
class SimonMode : public Mode {
public:
  explicit SimonMode(Player& owner) : Mode(owner) {}
  void Begin(uint32_t now_ms) override;
  void Update(uint32_t now_ms) override;

private:
  enum class Phase : uint8_t { Show, Input, Result };

  void Extend();
  void StartShow(uint32_t now_ms);
  void UpdateShow(uint32_t now_ms);
  void UpdateInput(uint32_t now_ms);
  void Finish(bool passed, uint32_t now_ms);

  uint8_t _sequence[config::kSimonMaxLength] = {};
  uint8_t _length = 0;
  uint8_t _step = 0; // the next sequence index the player has to press
  Phase _phase = Phase::Show;
  uint32_t _phase_ms = 0;
  uint32_t _last_press_ms = 0;
  int8_t _lit = -1;  // cap lit by the show, -1 when dark
  int8_t _echo = -1; // cap lit by the player's own press
  uint32_t _echo_ms = 0;
};

// --- Every mode, for one player --------------------------------------------
//
// Members are generated from MODE_LIST, so a new mode is a line there plus its
// class above, and forgetting the class is a compile error rather than a gap.
class PlayerModes {
public:
  explicit PlayerModes(Player& owner);
  Mode& Get(ModeId id);

private:
#define X(id, cls, member, banner, ms) cls member;
  MODE_LIST(X)
#undef X
  // The constructor initializes the members above from MODE_LIST, one entry
  // and one trailing comma each; this gives that list something to end on.
  [[maybe_unused]] uint8_t _end;
};

#endif
