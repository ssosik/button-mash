// Just enough of Arduino.h to compile the game logic on a host computer, so
// `make test` can play every mode without a Teensy attached. The real build
// never sees this file.
#ifndef Arduino_h
#define Arduino_h

#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

typedef uint8_t byte;

#define INPUT 0x0
#define OUTPUT 0x1
#define INPUT_PULLUP 0x2
#define LOW 0x0
#define HIGH 0x1
#define DMAMEM
#define F(s) (s)

inline void pinMode(uint8_t, uint8_t) {}
inline void digitalWrite(uint8_t, uint8_t) {}
inline int digitalRead(uint8_t) { return HIGH; }
inline int analogRead(uint8_t) { return 0; }

// Deterministic, so a failing run replays exactly. Defined in the test.
long random(long howbig);
long random(long howsmall, long howbig);
void randomSeed(unsigned long seed);

#endif
