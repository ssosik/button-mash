#include "ButtonInput.h"

// --- ButtonInput ------------------------------------------------------------

void ButtonInput::Poll(uint32_t now_ms) {
  bool raw[config::kInputsPerPlayer];
  ReadRaw(raw);

  for (uint8_t i = 0; i < config::kInputsPerPlayer; i++) {
    if (raw[i] != _candidate[i]) {
      // Reading moved; restart this input's settling window.
      _candidate[i] = raw[i];
      _changed_at[i] = now_ms;
      continue;
    }

    if (_candidate[i] == _stable[i]) {
      continue;
    }

    if (now_ms - _changed_at[i] < config::kDebounceMs) {
      continue;
    }

    _stable[i] = _candidate[i];
    if (_stable[i]) {
      // Rising edge only. A held button latches exactly once.
      _press_latch[i] = true;
    }
  }
}

bool ButtonInput::TakePress(uint8_t index) {
  if (index >= config::kInputsPerPlayer) {
    return false;
  }
  const bool pressed = _press_latch[index];
  _press_latch[index] = false;
  return pressed;
}

bool ButtonInput::IsDown(uint8_t index) const {
  if (index >= config::kInputsPerPlayer) {
    return false;
  }
  return _stable[index];
}

int8_t ButtonInput::DownIndex() const {
  for (uint8_t i = 0; i < config::kInputsPerPlayer; i++) {
    if (_stable[i]) {
      return (int8_t) i;
    }
  }
  return -1;
}

void ButtonInput::ClearPresses() {
  for (uint8_t i = 0; i < config::kInputsPerPlayer; i++) {
    _press_latch[i] = false;
  }
}

// --- LadderInput ------------------------------------------------------------

LadderInput::LadderInput(uint8_t analog_pin) : _pin(analog_pin) {}

void LadderInput::Begin() {
  pinMode(_pin, INPUT);
}

int8_t LadderInput::Decode(int adc_value) {
  if (adc_value <= config::kLadderIdleCeiling) {
    return -1;
  }

  for (uint8_t i = 0; i < config::kInputsPerPlayer; i++) {
    const int lower = config::kLadderThresholds[i] - config::kLadderTolerance;
    const int upper = config::kLadderThresholds[i] + config::kLadderTolerance;
    if (adc_value >= lower && adc_value <= upper) {
      return (int8_t) i;
    }
  }

  // Between two windows: either a simultaneous press the ladder cannot
  // represent, or a threshold that needs recalibrating.
  return -1;
}

void LadderInput::ReadRaw(bool out[config::kInputsPerPlayer]) {
  _last_raw = analogRead(_pin);
  const int8_t index = Decode(_last_raw);

  for (uint8_t i = 0; i < config::kInputsPerPlayer; i++) {
    out[i] = (index == (int8_t) i);
  }
}

// --- GpioInput --------------------------------------------------------------

GpioInput::GpioInput(const uint8_t pins[config::kInputsPerPlayer]) : _pins(pins) {}

void GpioInput::Begin() {
  for (uint8_t i = 0; i < config::kInputsPerPlayer; i++) {
    pinMode(_pins[i], INPUT_PULLUP);
  }
}

void GpioInput::ReadRaw(bool out[config::kInputsPerPlayer]) {
  for (uint8_t i = 0; i < config::kInputsPerPlayer; i++) {
    // Switch to ground, so LOW means pressed.
    out[i] = (digitalRead(_pins[i]) == LOW);
  }
}
