#ifndef ButtonInput_h
#define ButtonInput_h

#include "Config.h"
#include <Arduino.h>

// ---------------------------------------------------------------------------
// One player's buttons, behind an interface that hides whether they arrive on
// an analog resistor ladder or on individual GPIOs.
//
// Debounce and edge detection live in the base class so both hardware paths
// behave identically. Subclasses only answer "which buttons are physically
// down right now".
//
// The original code had neither: Player::Debounced() was a 200 ms rate limiter
// that re-fired for as long as a button was held, so a player could farm points
// by leaning on a cap whenever random() picked the same mole twice.
// ---------------------------------------------------------------------------

class ButtonInput {
public:
  virtual ~ButtonInput() = default;

  // Configure pins. Must be called from setup(), never from a constructor.
  virtual void Begin() = 0;

  // Sample the hardware and update debounced state. Safe to call as fast as
  // loop() runs.
  void Poll(uint32_t now_ms);

  // True exactly once per physical press. Consuming: clears the latch.
  bool TakePress(uint8_t index);

  // Debounced level, for hold-to-activate gestures like the debug entry combo.
  bool IsDown(uint8_t index) const;

  // Lowest index currently held, or -1 if none. Used by the debug screens.
  int8_t DownIndex() const;

  // Discard any latched presses, so a stale press cannot leak across a state
  // change.
  void ClearPresses();

  // Raw ADC reading for the debug and calibration screens. Returns -1 on
  // hardware that has no single raw value.
  virtual int RawValue() const { return -1; }

protected:
  // Fill `out` with the instantaneous, undebounced state of each input.
  virtual void ReadRaw(bool out[config::kInputsPerPlayer]) = 0;

private:
  bool _stable[config::kInputsPerPlayer] = {};
  bool _candidate[config::kInputsPerPlayer] = {};
  uint32_t _changed_at[config::kInputsPerPlayer] = {};
  bool _press_latch[config::kInputsPerPlayer] = {};
};

// --- Analog resistor ladder -------------------------------------------------
//
// All of a player's buttons in series with 10K resistors on one analog pin.
// Cheap in wiring, but two buttons pressed together produce an intermediate
// voltage that decodes as a third button. Superseded by GpioInput.
class LadderInput : public ButtonInput {
public:
  explicit LadderInput(uint8_t analog_pin);

  void Begin() override;
  int RawValue() const override { return _last_raw; }

  // Decode an ADC reading to a button index, or -1 for none. Exposed for the
  // calibration screen.
  static int8_t Decode(int adc_value);

protected:
  void ReadRaw(bool out[config::kInputsPerPlayer]) override;

private:
  uint8_t _pin;
  int _last_raw = 0;
};

// --- One GPIO per button ----------------------------------------------------
//
// Switch to ground against INPUT_PULLUP. Needs one more conductor per button
// than the ladder, but reads simultaneous presses correctly and needs no
// threshold calibration at all.
class GpioInput : public ButtonInput {
public:
  explicit GpioInput(const uint8_t pins[config::kInputsPerPlayer]);

  void Begin() override;

protected:
  void ReadRaw(bool out[config::kInputsPerPlayer]) override;

private:
  const uint8_t* _pins;
};

#endif
