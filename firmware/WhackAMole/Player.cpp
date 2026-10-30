#include "Player.h"

Player::Player(const char* name, ButtonInput& input, Lights& lights)
    : _name(name), _input(&input), _lights(&lights) {}

void Player::Begin() {
  _input->Begin();
  _lights->Begin();
  _lights->Clear();
}

void Player::Reset() {
  _total_score = 0;
  _is_ready = false;
  _lights->Clear();
  _input->ClearPresses();
}

void Player::NotReady() {
  _is_ready = false;
  _lights->Clear();
}

bool Player::TakeStartPress() {
  return _input->TakePress(config::kStartButtonIndex);
}

void Player::Penalize(int points) {
  _total_score -= points;
  if (_total_score < 0) {
    _total_score = 0;
  }
}
