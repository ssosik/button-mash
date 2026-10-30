#ifndef Player_h
#define Player_h

#include "ButtonInput.h"
#include "Config.h"
#include "Lights.h"
#include <Arduino.h>

// ---------------------------------------------------------------------------
// One player's buttons, lamps, score, and whether they are in the game.
//
// What a press *means* lives in the modes (Mode.h), not here. This class used
// to hold the whole mole game as well, which left no room for a second way to
// play; now it is the hardware and the score, and each mode drives it.
// ---------------------------------------------------------------------------

class Player {
public:
  Player(const char* name, ButtonInput& input, Lights& lights);

  // Configure hardware. Called from setup(), not from the constructor.
  void Begin();

  // Clear score and lamps and drop out of the game.
  void Reset();

  void Ready() { _is_ready = true; }
  void NotReady();
  bool IsReady() const { return _is_ready; }

  // True exactly once per press of this player's start button.
  bool TakeStartPress();

  void AddPoints(int points) { _total_score += points; }

  // Deduct, flooring at zero. The original guard skipped the penalty entirely
  // whenever the score was below it, so a losing player was immune.
  void Penalize(int points);

  int Score() const { return _total_score; }
  const char* Name() const { return _name; }

  ButtonInput& Input() { return *_input; }
  Lights& Lamps() { return *_lights; }

private:
  const char* _name;
  ButtonInput* _input;
  Lights* _lights;

  int _total_score = 0;
  bool _is_ready = false;
};

#endif
