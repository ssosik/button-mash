#ifndef Game_h
#define Game_h

#include "Config.h"
#include "Debug.h"
#include "Mode.h"
#include "Player.h"
#include <Arduino.h>

// ---------------------------------------------------------------------------
// The state list, its display names, and its timeouts in one table.
//
// These used to be an enum and a separate array that happened to be in the same
// order, indexed by position with nothing enforcing the correspondence. Adding
// a state in the wrong place would have silently given every state after it the
// wrong timeout. Generating both from one list makes that impossible.
//
//     X(enum name, log label, timeout in ms)
// ---------------------------------------------------------------------------
#define GAME_STATE_LIST(X)                                                                         \
  /* Powered on, nothing initialized yet. */                                                       \
  X(Boot, "BOOT", 200)                                                                             \
  /* Announce ourselves to the display. */                                                         \
  X(SendConReady, "SENDCONREADY", 1000)                                                            \
  /* Wait for the display to answer; retry on timeout. */                                          \
  X(DisplayReadyWait, "DISPLAYREADYWAIT", 10000)                                                   \
  X(Initialized, "INITIALIZED", 200)                                                               \
  /* Clear scores and lamps for a fresh game. */                                                   \
  X(NewGame, "NEWGAME", 200)                                                                       \
  /* Attract loop: splash, high score, press start. */                                             \
  X(ShowSplash, "SHOWSPLASH", 8000)                                                                \
  X(ShowHighScore, "SHOWHIGHSCORE", 10000)                                                         \
  X(ShowPressStart, "SHOWPRESSSTART", 10000)                                                       \
  /* One player is in; hold briefly for the other. */                                              \
  X(P1Ready, "P1READY", 10000)                                                                     \
  X(P2Ready, "P2READY", 10000)                                                                     \
  X(StartCountdownReady, "STARTREADY", 2000)                                                       \
  X(StartCountdownSet, "STARTSET", 2000)                                                           \
  X(StartCountdownGo, "STARTGO", 1000)                                                             \
  /* Start the medley at its first mode. */                                                       \
  X(StartGame, "STARTGAME", 200)                                                                   \
  /* Banner naming the next mode, lamps dark. */                                                   \
  X(ModeIntro, "MODEINTRO", config::kModeIntroMs)                                                  \
  /* One mode's segment. Ends at that mode's own length; see MODE_LIST. */                        \
  X(PlayGame, "PLAYGAME", 0)                                                                       \
  X(GameEnd, "GAMEEND", 200)                                                                       \
  X(ShowWinner, "SHOWWINNER", 10000)                                                               \
  /* Hardware test screens; leaves only when the operator asks. */                                  \
  X(DebugMode, "DEBUGMODE", 0)

enum GameState : uint8_t {
#define X(name, label, timeout) name,
  GAME_STATE_LIST(X)
#undef X
  GameStateCount
};

class Game {
public:
  Game(Player& p1, Player& p2);

  // Open the serial ports and configure player hardware. Call from setup().
  void Begin();

  // Sample buttons. Call every pass through loop().
  void PollInputs(uint32_t now_ms);

  // Advance the state machine. Call every config::kTickIntervalMs.
  void Tick(uint32_t now_ms);

private:
  void NextState(GameState state, uint32_t now_ms);
  bool StateTimedOut(uint32_t now_ms) const;

  // Send a status message, suppressing exact repeats.
  void SendMessage(const char* message);

  // Send the live score, suppressing repeats. Kept separate from SendMessage
  // because the two used to share one "last message" buffer and cancel each
  // other out, so scores stopped updating whenever a status message repeated.
  void SendScore(int p1_score, int p2_score);

  // Accumulate display bytes until a full '\n'-terminated line arrives.
  bool ReadDisplayLine();

  // True once both start buttons have been held together long enough.
  bool DebugComboHeld(uint32_t now_ms);

  // Attract-mode states share this: start press enters the game, combo enters
  // debug. Returns true if a transition happened.
  bool HandleAttractInput(uint32_t now_ms);

  // Medley plumbing: dark lamps and a banner between segments, then the next
  // mode begun for every player who is in.
  void EnterModeIntro(uint32_t now_ms);
  void StartMode(uint32_t now_ms);
  ModeId CurrentMode() const { return (ModeId) _mode_index; }

  // Flush both players' staged lamp changes in one go. See Mode.h.
  void ShowLamps();
  void ClearLamps();

  // Send each player's target colour, suppressing repeats like SendScore.
  void SendTargets();

  GameState _state = Boot;
  uint32_t _state_entered_ms = 0;

  Player* _p1;
  Player* _p2;
  Debug _debug;
  PlayerModes _p1_modes;
  PlayerModes _p2_modes;
  uint8_t _mode_index = 0;

  char _last_message[48] = {};
  int _last_p1_score = -1;
  int _last_p2_score = -1;
  char _last_targets[48] = {}; // "#TARGET:RRGGBB,WHITE:RRGGBB,WHITE" fits

  char _rx_buf[48] = {};
  uint8_t _rx_len = 0;

  uint32_t _combo_started_ms = 0;
  bool _combo_active = false;

  // Start presses seen but not yet acted on, indexed P1, P2. See
  // HandleAttractInput and config::kStartArbitrationMs.
  uint32_t _start_pending_ms[2] = {0, 0};
  bool _start_pending[2] = {false, false};
};

#endif
