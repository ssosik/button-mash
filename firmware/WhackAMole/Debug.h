#ifndef Debug_h
#define Debug_h

#include "Config.h"
#include "Player.h"
#include <Arduino.h>

// ---------------------------------------------------------------------------
// Hardware test screens, reachable from attract mode by holding both start
// buttons.
//
// Everything reports to USB serial and mirrors a short banner onto the LED
// matrix, so the table can be tested standing up with no laptop attached.
//
// Navigation:
//   P1 start  - next screen
//   P2 start  - act within the current screen (advance a calibration step,
//               restart a sweep)
//   both held - leave debug mode
// ---------------------------------------------------------------------------

enum class DebugScreen : uint8_t {
  LedWalk,     // light each cap in turn, naming it
  LedAll,      // every cap on solid, for current draw and brightness checks
  ButtonRead,  // live raw values and decoded button names
  Calibrate,   // measure the ladder and emit a paste-ready threshold table
  DisplayTest, // send every protocol message so the display can be verified
  Count
};

class Debug {
public:
  Debug(Player& p1, Player& p2);

  void Enter(uint32_t now_ms);
  void Exit();

  void Update(uint32_t now_ms);

  // Short text for the LED matrix. Changes only when the screen state changes,
  // so the caller can suppress repeats.
  const char* Banner() const { return _banner; }

private:
  void NextScreen(uint32_t now_ms);
  void EnterScreen(DebugScreen screen, uint32_t now_ms);
  void SetBanner(const char* text);

  void UpdateLedWalk(uint32_t now_ms);
  void UpdateLedAll(uint32_t now_ms);
  void UpdateButtonRead(uint32_t now_ms);
  void UpdateCalibrate(uint32_t now_ms);
  void UpdateDisplayTest(uint32_t now_ms);

  // Consume any queued presses so navigation cannot be double-counted.
  void DrainPresses();

  Player* _players[2];
  DebugScreen _screen = DebugScreen::LedWalk;
  uint32_t _screen_entered_ms = 0;
  uint32_t _last_step_ms = 0;
  char _banner[24] = {};

  // LedWalk
  uint8_t _walk_index = 0;
  uint8_t _walk_color = 0;

  // ButtonRead
  uint32_t _last_report_ms = 0;

  // Calibrate
  enum class CalPhase : uint8_t { Prompt, Sampling, WaitRelease, Done };
  CalPhase _cal_phase = CalPhase::Prompt;
  uint8_t _cal_player = 0;
  uint8_t _cal_index = 0;
  uint8_t _cal_samples = 0;
  uint32_t _cal_accumulator = 0;
  int _cal_result[2][config::kInputsPerPlayer] = {};

  // DisplayTest
  uint8_t _display_test_index = 0;
};

#endif
