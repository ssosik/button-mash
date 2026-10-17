#include "Game.h"
#include "Protocol.h"

namespace {

// Generated from the same list as the enum, so the two cannot drift apart.
const char* const kStateNames[GameStateCount] = {
#define X(name, label, timeout) label,
    GAME_STATE_LIST(X)
#undef X
};

constexpr uint32_t kStateTimeoutMs[GameStateCount] = {
#define X(name, label, timeout) timeout,
    GAME_STATE_LIST(X)
#undef X
};

} // namespace

Game::Game(Player& p1, Player& p2) : _p1(&p1), _p2(&p2), _debug(p1, p2) {}

void Game::Begin() {
  // All hardware setup happens here rather than in constructors. The originals
  // called pinMode(), Serial.print(), and Serial2.begin() from global object
  // constructors, which run before the core has finished bringing the
  // peripherals up.
  Serial.begin(115200);
  WAM_DISPLAY_SERIAL.begin(config::kDisplayBaud);

  randomSeed((unsigned long) analogRead(config::kFloatingSeedPin));

  _p1->Begin();
  _p2->Begin();

  Serial.println(F("Whack A Mole Attack: controller boot"));
  NextState(Boot, millis());
}

void Game::NextState(GameState state, uint32_t now_ms) {
  _state = state;
  _state_entered_ms = now_ms;
  Serial.print(F("Next State: "));
  Serial.println(kStateNames[state]);
}

bool Game::StateTimedOut(uint32_t now_ms) const {
  const uint32_t timeout = kStateTimeoutMs[_state];
  if (timeout == 0) {
    return false; // states that only leave on an explicit event
  }
  return (now_ms - _state_entered_ms) >= timeout;
}

void Game::SendMessage(const char* message) {
  if (strncmp(_last_message, message, sizeof(_last_message)) == 0) {
    return;
  }
  strncpy(_last_message, message, sizeof(_last_message) - 1);
  _last_message[sizeof(_last_message) - 1] = '\0';

  WAM_DISPLAY_SERIAL.print(message);
  WAM_DISPLAY_SERIAL.print(protocol::kTerminator);
  Serial.println(message);
}

void Game::SendScore(int p1_score, int p2_score) {
  if (p1_score == _last_p1_score && p2_score == _last_p2_score) {
    return;
  }
  _last_p1_score = p1_score;
  _last_p2_score = p2_score;

  char line[32];
  snprintf(line, sizeof(line), "%s%d:%d", protocol::kScore, p1_score, p2_score);
  WAM_DISPLAY_SERIAL.print(line);
  WAM_DISPLAY_SERIAL.print(protocol::kTerminator);
}

bool Game::ReadDisplayLine() {
  while (WAM_DISPLAY_SERIAL.available() > 0) {
    const int byte_in = WAM_DISPLAY_SERIAL.read();
    if (byte_in < 0) {
      break;
    }

    if (byte_in == '\n' || byte_in == '\r') {
      if (_rx_len == 0) {
        continue; // skip the empty half of a CRLF
      }
      _rx_buf[_rx_len] = '\0';
      _rx_len = 0;
      return true;
    }

    if (_rx_len < sizeof(_rx_buf) - 1) {
      _rx_buf[_rx_len++] = (char) byte_in;
    } else {
      _rx_len = 0; // overlong line, resynchronise
    }
  }
  return false;
}

bool Game::DebugComboHeld(uint32_t now_ms) {
  const bool both_down = _p1->Input().IsDown(config::kStartButtonIndex) &&
                         _p2->Input().IsDown(config::kStartButtonIndex);

  if (!both_down) {
    _combo_active = false;
    return false;
  }

  if (!_combo_active) {
    _combo_active = true;
    _combo_started_ms = now_ms;
    return false;
  }

  if (now_ms - _combo_started_ms < config::kDebugEntryHoldMs) {
    return false;
  }

  // Latch off so one long hold fires exactly once.
  _combo_active = false;
  return true;
}

bool Game::HandleAttractInput(uint32_t now_ms) {
  if (DebugComboHeld(now_ms)) {
    _start_pending[0] = false;
    _start_pending[1] = false;
    _debug.Enter(now_ms);
    NextState(DebugMode, now_ms);
    return true;
  }

  // Record the press, but do not act on it yet. The debug gesture is both
  // start buttons held together for two seconds, so acting the moment the
  // first one latches would leave attract mode before the second finger
  // landed and the combo could never complete. See kStartArbitrationMs.
  if (_p1->TakeStartPress()) {
    _start_pending[0] = true;
    _start_pending_ms[0] = now_ms;
  }
  if (_p2->TakeStartPress()) {
    _start_pending[1] = true;
    _start_pending_ms[1] = now_ms;
  }

  // Once both are down this is a debug attempt, not a game start. Drop the
  // pending presses and let DebugComboHeld own it; a combo that is abandoned
  // before the hold completes then correctly does nothing at all.
  if (_p1->Input().IsDown(config::kStartButtonIndex) &&
      _p2->Input().IsDown(config::kStartButtonIndex)) {
    _start_pending[0] = false;
    _start_pending[1] = false;
    return false;
  }

  // Checked in order and returned immediately. The original checked both
  // players in sequence with no early exit, so a simultaneous press left P2
  // overwriting the transition P1 had just made. Both pending flags are
  // cleared on the way out so a stale one cannot fire on a later visit here.
  if (_start_pending[0] &&
      now_ms - _start_pending_ms[0] >= config::kStartArbitrationMs) {
    _start_pending[0] = false;
    _start_pending[1] = false;
    _p1->Ready(now_ms);
    NextState(P1Ready, now_ms);
    return true;
  }

  if (_start_pending[1] &&
      now_ms - _start_pending_ms[1] >= config::kStartArbitrationMs) {
    _start_pending[0] = false;
    _start_pending[1] = false;
    _p2->Ready(now_ms);
    NextState(P2Ready, now_ms);
    return true;
  }

  return false;
}

void Game::PollInputs(uint32_t now_ms) {
  _p1->Input().Poll(now_ms);
  _p2->Input().Poll(now_ms);
}

void Game::Tick(uint32_t now_ms) {
  char line[32];

  switch (_state) {
  case Boot:
#if WAM_BOOT_TO_DEBUG
    _debug.Enter(now_ms);
    NextState(DebugMode, now_ms);
#else
    NextState(SendConReady, now_ms);
#endif
    break;

  case SendConReady:
    _last_message[0] = '\0';
    SendMessage(protocol::kConReady);
    NextState(DisplayReadyWait, now_ms);
    break;

  case DisplayReadyWait:
    // The debug combo is honoured here, not only in the attract states. Without
    // this the test screens are unreachable whenever the display does not
    // answer -- which is every bench session before the Matrix Portal is wired,
    // and any future session where the display has failed. Being locked out of
    // the diagnostics exactly when something is broken is the wrong behaviour.
    if (DebugComboHeld(now_ms)) {
      _debug.Enter(now_ms);
      NextState(DebugMode, now_ms);
      break;
    }

    if (ReadDisplayLine() && strcmp(_rx_buf, protocol::kDisplayReady) == 0) {
      NextState(Initialized, now_ms);
      break;
    }
    if (StateTimedOut(now_ms)) {
      NextState(SendConReady, now_ms); // re-announce and try again
    }
    break;

  case Initialized:
    NextState(NewGame, now_ms);
    break;

  case NewGame:
    _p1->Reset();
    _p2->Reset();
    _last_p1_score = -1;
    _last_p2_score = -1;
    SendMessage(protocol::kNewGame);
    NextState(ShowSplash, now_ms);
    break;

  case ShowSplash:
    SendMessage(protocol::kShowSplash);
    if (HandleAttractInput(now_ms)) {
      break;
    }
    if (StateTimedOut(now_ms)) {
      NextState(ShowHighScore, now_ms);
    }
    break;

  case ShowHighScore:
    SendMessage(protocol::kShowHighScore);
    if (HandleAttractInput(now_ms)) {
      break;
    }
    if (StateTimedOut(now_ms)) {
      NextState(ShowPressStart, now_ms);
    }
    break;

  case ShowPressStart:
    SendMessage(protocol::kShowPressStart);
    if (HandleAttractInput(now_ms)) {
      break;
    }
    if (StateTimedOut(now_ms)) {
      NextState(ShowSplash, now_ms);
    }
    break;

  case P1Ready:
    SendMessage(protocol::kIsP2Ready);
    if (_p2->TakeStartPress()) {
      _p2->Ready(now_ms);
      NextState(StartCountdownReady, now_ms);
      break;
    }
    if (StateTimedOut(now_ms)) {
      NextState(StartCountdownReady, now_ms); // single player
    }
    break;

  case P2Ready:
    SendMessage(protocol::kIsP1Ready);
    if (_p1->TakeStartPress()) {
      _p1->Ready(now_ms);
      NextState(StartCountdownReady, now_ms);
      break;
    }
    if (StateTimedOut(now_ms)) {
      NextState(StartCountdownReady, now_ms);
    }
    break;

  case StartCountdownReady:
    SendMessage(protocol::kCountdownReady);
    if (StateTimedOut(now_ms)) {
      NextState(StartCountdownSet, now_ms);
    }
    break;

  case StartCountdownSet:
    SendMessage(protocol::kCountdownSet);
    if (StateTimedOut(now_ms)) {
      NextState(StartCountdownGo, now_ms);
    }
    break;

  case StartCountdownGo:
    SendMessage(protocol::kCountdownGo);
    if (StateTimedOut(now_ms)) {
      NextState(StartGame, now_ms);
    }
    break;

  case StartGame:
    // Discard anything mashed during the countdown so the round starts clean.
    _p1->Input().ClearPresses();
    _p2->Input().ClearPresses();
    _p1->NewMole(now_ms);
    _p2->NewMole(now_ms);
    NextState(PlayGame, now_ms);
    break;

  case PlayGame:
    _p1->Update(now_ms);
    _p2->Update(now_ms);
    SendScore(_p1->Score(), _p2->Score());
    if (StateTimedOut(now_ms)) {
      NextState(GameEnd, now_ms);
    }
    break;

  case GameEnd:
    _p1->NotReady();
    _p2->NotReady();
    if (StateTimedOut(now_ms)) {
      NextState(ShowWinner, now_ms);
    }
    break;

  case ShowWinner: {
    const int p1_score = _p1->Score();
    const int p2_score = _p2->Score();

    if (p1_score == p2_score) {
      snprintf(line, sizeof(line), "%s%d", protocol::kTieGame, p1_score);
    } else if (p1_score > p2_score) {
      snprintf(line, sizeof(line), "%s%d", protocol::kPlayer1Win, p1_score);
    } else {
      snprintf(line, sizeof(line), "%s%d", protocol::kPlayer2Win, p2_score);
    }
    SendMessage(line);

    // Either player can start the next round straight from the results screen.
    if (_p1->TakeStartPress()) {
      _p1->Reset();
      _p2->Reset();
      _p1->Ready(now_ms);
      NextState(P1Ready, now_ms);
      break;
    }
    if (_p2->TakeStartPress()) {
      _p1->Reset();
      _p2->Reset();
      _p2->Ready(now_ms);
      NextState(P2Ready, now_ms);
      break;
    }

    if (StateTimedOut(now_ms)) {
      NextState(NewGame, now_ms);
    }
    break;
  }

  case DebugMode: {
    if (DebugComboHeld(now_ms)) {
      _debug.Exit();
      _last_message[0] = '\0'; // debug wrote to the display behind our back
      NextState(NewGame, now_ms);
      break;
    }

    _debug.Update(now_ms);

    snprintf(line, sizeof(line), "%s%s", protocol::kDebug, _debug.Banner());
    SendMessage(line);
    break;
  }

  case GameStateCount:
    break;
  }
}
