#include "Debug.h"
#include "Protocol.h"

namespace {

// Cap colours, in wiring order, with the start button last.
const char* const kButtonNames[config::kInputsPerPlayer] = {"BLUE",   "RED",    "WHITE",
                                                            "GREEN",  "YELLOW", "START"};

const char* const kScreenNames[(uint8_t) DebugScreen::Count] = {
    "LED WALK", "LED ALL", "BUTTONS", "CALIBRATE", "DISPLAY"};

// Every cap shows this sequence before the walk moves on. The three primaries
// come first and white last: a channel that is dead shows as a cap that skips
// one colour, and a ring expecting a different byte order shows as the names
// not matching what you see. White alone -- the old behaviour -- lights all
// three channels at once and hides both faults.
struct WalkColor {
  Color color;
  const char* name;
};
const WalkColor kWalkColors[] = {
    {colors::kRed, "RED"},
    {colors::kGreen, "GREEN"},
    {colors::kBlue, "BLUE"},
    {colors::kWhite, "WHITE"},
};
constexpr uint8_t kWalkColorCount = sizeof(kWalkColors) / sizeof(kWalkColors[0]);

// Every controller-to-display message, so the display side can be exercised
// end to end without playing a round.
const char* const kDisplayTestMessages[] = {
    protocol::kNewGame,         protocol::kShowSplash,     protocol::kShowHighScore,
    protocol::kShowPressStart,  protocol::kIsP1Ready,      protocol::kIsP2Ready,
    protocol::kCountdownReady,  protocol::kCountdownSet,   protocol::kCountdownGo,
    "#PLAYER1WIN:12345",        "#PLAYER2WIN:12345",       "#TIEGAME:12345",
    "#MODE:CHASE",              "#SCORE:1234:5678",        "#TARGET:FF0000:00FF00",
    "#TARGET:-:-",
};
constexpr uint8_t kDisplayTestCount =
    sizeof(kDisplayTestMessages) / sizeof(kDisplayTestMessages[0]);

constexpr uint32_t kButtonReportIntervalMs = 250;
constexpr uint32_t kDisplayTestIntervalMs = 1500;

uint8_t LedPinFor(uint8_t player, uint8_t index) {
  const uint8_t* pins = (player == 0) ? config::kP1LedPins : config::kP2LedPins;
  return pins[index];
}

} // namespace

Debug::Debug(Player& p1, Player& p2) {
  _players[0] = &p1;
  _players[1] = &p2;
}

void Debug::Enter(uint32_t now_ms) {
  Serial.println();
  Serial.println(F("=== DEBUG MODE ==="));
  Serial.println(F("P1 start: next screen   P2 start: act   both: exit"));
#if WAM_INPUT_GPIO
  Serial.println(F("Input: one GPIO per button"));
#else
  Serial.println(F("Input: analog resistor ladder"));
#endif
#if WAM_LIGHTS_PIXELS
  Serial.println(F("Lights: WS2812 pixels"));
#else
  Serial.println(F("Lights: digital dome lamps"));
#endif

  DrainPresses();
  EnterScreen(DebugScreen::LedWalk, now_ms);
}

void Debug::Exit() {
  for (auto* player : _players) {
    player->Lamps().Clear();
  }
  DrainPresses();
  Serial.println(F("=== LEAVING DEBUG MODE ==="));
}

void Debug::DrainPresses() {
  for (auto* player : _players) {
    player->Input().ClearPresses();
  }
}

void Debug::SetBanner(const char* text) {
  strncpy(_banner, text, sizeof(_banner) - 1);
  _banner[sizeof(_banner) - 1] = '\0';
}

void Debug::NextScreen(uint32_t now_ms) {
  const uint8_t next = ((uint8_t) _screen + 1) % (uint8_t) DebugScreen::Count;
  EnterScreen((DebugScreen) next, now_ms);
}

void Debug::EnterScreen(DebugScreen screen, uint32_t now_ms) {
  _screen = screen;
  _screen_entered_ms = now_ms;
  _last_step_ms = now_ms;

  for (auto* player : _players) {
    player->Lamps().Clear();
  }

  _walk_index = 0;
  _walk_color = 0;
  _display_test_index = 0;
  _cal_phase = CalPhase::Prompt;
  _cal_player = 0;
  _cal_index = 0;
  _cal_samples = 0;
  _cal_accumulator = 0;

  Serial.println();
  Serial.print(F("--- "));
  Serial.print(kScreenNames[(uint8_t) screen]);
  Serial.println(F(" ---"));

  SetBanner(kScreenNames[(uint8_t) screen]);
}

void Debug::Update(uint32_t now_ms) {
  // P1 start advances the screen. Checked before the per-screen handlers so a
  // screen cannot swallow the navigation press.
  if (_players[0]->Input().TakePress(config::kStartButtonIndex)) {
    NextScreen(now_ms);
    return;
  }

  switch (_screen) {
  case DebugScreen::LedWalk:
    UpdateLedWalk(now_ms);
    break;
  case DebugScreen::LedAll:
    UpdateLedAll(now_ms);
    break;
  case DebugScreen::ButtonRead:
    UpdateButtonRead(now_ms);
    break;
  case DebugScreen::Calibrate:
    UpdateCalibrate(now_ms);
    break;
  case DebugScreen::DisplayTest:
    UpdateDisplayTest(now_ms);
    break;
  case DebugScreen::Count:
    break;
  }
}

// Light every cap in turn, both players, naming each one as it comes up. Each
// cap steps through every colour before the walk moves on, so one pass tests
// the wiring and all three colour channels together. A cap that stays dark is a
// wiring fault; a cap that skips a colour is a dead channel; a cap whose colour
// does not match the name is a ring expecting a different byte order.
void Debug::UpdateLedWalk(uint32_t now_ms) {
  if (now_ms - _last_step_ms < config::kDebugLedWalkMs) {
    return;
  }
  _last_step_ms = now_ms;

  const uint8_t total = config::kButtonsPerPlayer * 2;
  const uint8_t player = _walk_index / config::kButtonsPerPlayer;
  const uint8_t index = _walk_index % config::kButtonsPerPlayer;
  const WalkColor& step = kWalkColors[_walk_color];

  for (auto* p : _players) {
    p->Lamps().Clear();
  }
  _players[player]->Lamps().Set(index, step.color);
  _players[player]->Lamps().Show();

  char line[64];
  snprintf(line, sizeof(line), "%s %s %s (pin %u)", _players[player]->Name(),
           kButtonNames[index], step.name, (unsigned) LedPinFor(player, index));
  Serial.println(line);

  // The banner is 24 characters, so it gets the short form without the pin.
  char banner[24];
  snprintf(banner, sizeof(banner), "%s %s %s", _players[player]->Name(), kButtonNames[index],
           step.name);
  SetBanner(banner);

  // Advance the colour first; the cap only changes once it has shown them all.
  _walk_color = (uint8_t) (_walk_color + 1);
  if (_walk_color >= kWalkColorCount) {
    _walk_color = 0;
    _walk_index = (uint8_t) ((_walk_index + 1) % total);
  }
}

// Everything on solid: the screen to sit on with a meter on the 5 V rail.
void Debug::UpdateLedAll(uint32_t now_ms) {
  (void) now_ms;
  if (_walk_index != 0) {
    return; // already latched on; nothing to repeat
  }
  _walk_index = 1;

  for (auto* p : _players) {
    p->Lamps().SetAll(colors::kWhite);
  }
  Serial.println(F("All lamps on. Measure the 5V rail here."));
  SetBanner("ALL ON");
}

// Live view of what the input layer is actually reading.
void Debug::UpdateButtonRead(uint32_t now_ms) {
  bool any_named = false;
  char banner[24] = "NONE";

  for (uint8_t p = 0; p < 2; p++) {
    const int8_t down = _players[p]->Input().DownIndex();
    if (down >= 0) {
      // Short enough for the panel to show still: "P1 B3", or "P2 ST" for the
      // start button. Serial below still names the colour.
      if (down == config::kStartButtonIndex) {
        snprintf(banner, sizeof(banner), "%s ST", _players[p]->Name());
      } else {
        snprintf(banner, sizeof(banner), "%s B%d", _players[p]->Name(), down + 1);
      }
      any_named = true;
    }
  }
  if (!any_named) {
    SetBanner("NONE");
  } else {
    SetBanner(banner);
  }

  if (now_ms - _last_report_ms < kButtonReportIntervalMs) {
    return;
  }
  _last_report_ms = now_ms;

  char line[96];
  const int8_t d0 = _players[0]->Input().DownIndex();
  const int8_t d1 = _players[1]->Input().DownIndex();
  snprintf(line, sizeof(line), "P1 raw=%5d %-7s | P2 raw=%5d %-7s",
           _players[0]->Input().RawValue(), d0 >= 0 ? kButtonNames[d0] : "-",
           _players[1]->Input().RawValue(), d1 >= 0 ? kButtonNames[d1] : "-");
  Serial.println(line);
}

// Walk the operator through pressing every button, average the ADC reading for
// each, then print a table ready to paste into Config.h. This is what retires
// the hand-tuned kLadderThresholds values.
void Debug::UpdateCalibrate(uint32_t now_ms) {
  (void) now_ms;

#if WAM_INPUT_GPIO
  SetBanner("N/A ON GPIO");
  if (_cal_phase != CalPhase::Done) {
    _cal_phase = CalPhase::Done;
    Serial.println(F("Calibration is not needed with one GPIO per button."));
  }
  return;
#else
  ButtonInput& input = _players[_cal_player]->Input();

  switch (_cal_phase) {
  case CalPhase::Prompt: {
    char line[48];
    snprintf(line, sizeof(line), "PRESS %s %s", _players[_cal_player]->Name(),
             kButtonNames[_cal_index]);
    SetBanner(line);
    Serial.println(line);

    _cal_samples = 0;
    _cal_accumulator = 0;
    _cal_phase = CalPhase::Sampling;
    break;
  }

  case CalPhase::Sampling: {
    const int raw = input.RawValue();
    if (raw <= config::kLadderIdleCeiling) {
      break; // nothing held yet
    }

    _cal_accumulator += (uint32_t) raw;
    _cal_samples++;
    if (_cal_samples < config::kCalibrationSamples) {
      break;
    }

    const int average = (int) (_cal_accumulator / _cal_samples);
    _cal_result[_cal_player][_cal_index] = average;

    char line[48];
    snprintf(line, sizeof(line), "  %s %-7s = %d", _players[_cal_player]->Name(),
             kButtonNames[_cal_index], average);
    Serial.println(line);

    _cal_phase = CalPhase::WaitRelease;
    break;
  }

  case CalPhase::WaitRelease: {
    if (input.RawValue() > config::kLadderIdleCeiling) {
      break; // still held
    }

    _cal_index++;
    if (_cal_index < config::kInputsPerPlayer) {
      _cal_phase = CalPhase::Prompt;
      break;
    }

    _cal_index = 0;
    _cal_player++;
    if (_cal_player < 2) {
      _cal_phase = CalPhase::Prompt;
      break;
    }

    // Both ladders measured. Emit the table and a safe tolerance.
    Serial.println();
    Serial.println(F("Paste into Config.h:"));
    Serial.print(F("constexpr int kLadderThresholds[kInputsPerPlayer] = {"));

    int smallest_gap = 1024;
    for (uint8_t i = 0; i < config::kInputsPerPlayer; i++) {
      const int averaged = (_cal_result[0][i] + _cal_result[1][i]) / 2;
      Serial.print(averaged);
      if (i + 1 < config::kInputsPerPlayer) {
        Serial.print(F(", "));
      }

      // Gap against every other reading, not just the previous one: the
      // thresholds are not sorted by index.
      for (uint8_t j = 0; j < i; j++) {
        const int other = (_cal_result[0][j] + _cal_result[1][j]) / 2;
        const int gap = abs(averaged - other);
        if (gap < smallest_gap) {
          smallest_gap = gap;
        }
      }
    }
    Serial.println(F("};"));

    // Windows must not touch, so stay under half the closest spacing.
    const int suggested = (smallest_gap / 2) - 1;
    Serial.print(F("constexpr int kLadderTolerance = "));
    Serial.print(suggested > 0 ? suggested : 1);
    Serial.println(F(";"));

    if (suggested < 5) {
      Serial.println(F("WARNING: buttons are very close together. Check the ladder resistors."));
    }

    // Report per-player spread; a large difference means one ladder is off.
    for (uint8_t i = 0; i < config::kInputsPerPlayer; i++) {
      const int delta = abs(_cal_result[0][i] - _cal_result[1][i]);
      if (delta > config::kLadderTolerance) {
        char line[64];
        snprintf(line, sizeof(line), "NOTE: %s differs by %d between players",
                 kButtonNames[i], delta);
        Serial.println(line);
      }
    }

    SetBanner("CAL DONE");
    _cal_phase = CalPhase::Done;
    break;
  }

  case CalPhase::Done:
    // P2 start runs it again.
    if (_players[1]->Input().TakePress(config::kStartButtonIndex)) {
      EnterScreen(DebugScreen::Calibrate, now_ms);
    }
    break;
  }
#endif
}

// Cycle every protocol message so display/code.py can be checked against the
// full vocabulary without playing a round.
void Debug::UpdateDisplayTest(uint32_t now_ms) {
  if (_display_test_index > 0 && now_ms - _last_step_ms < kDisplayTestIntervalMs) {
    return;
  }
  _last_step_ms = now_ms;

  const char* message = kDisplayTestMessages[_display_test_index % kDisplayTestCount];
  WAM_DISPLAY_SERIAL.print(message);
  WAM_DISPLAY_SERIAL.print(protocol::kTerminator);
  Serial.print(F("sent "));
  Serial.println(message);

  _display_test_index = (uint8_t) ((_display_test_index + 1) % kDisplayTestCount);
}
