# CLAUDE.md

A two-player arcade table, "Cub Scout Button Mash". A Teensy 4.1 runs the game and drives
the button lamps; a Matrix Portal S3 only renders what the Teensy tells it on a 32×32
HUB75 panel. README.md is the user-facing guide; this file covers how to work on the code.

## Commands

```sh
make test                     # host tests: every game mode + the lamp dance, ASan/UBSan. Run after any firmware change.
make matrix                   # compile all four hardware configurations; must be warning-free
make upload                   # flash the table (defaults: GPIO buttons + WS2812 caps)
make lint CLANG_FORMAT="uvx --from clang-format==18.1.8 clang-format" RUFF="uvx ruff"
make check-pins               # docs/wiring.html pin tables vs Config.h
make wiring-pdf               # rebuild docs/mole-table-wiring.pdf (needs Chrome)
```

Neither clang-format nor ruff is necessarily installed; the `uvx` forms above match CI
(clang-format 18). CI (`.github/workflows/build.yml`) runs matrix, format, ruff on the whole
repo, check-pins, and `make test CXX=clang++`.

`Config.h` and the Makefile default to the real table (`GPIO=1 PIXELS=1`). `GPIO=0
PIXELS=0` builds for version 1's resistor ladder and dome lamps, kept compiling by CI.

## Layout

- `firmware/WhackAMole/`: Arduino sketch. `Config.h` holds every pin, timing value and
  tunable. `Protocol.h` is the wire protocol. `Game.cpp` is the state machine
  (`GAME_STATE_LIST` X-macro in `Game.h`). `Mode.h` has `MODE_LIST`, the medley of game
  modes, one `*Mode.cpp` each. `Dance.cpp` is the splash lamp show. `Debug.cpp` holds the
  hardware test screens.
- `firmware/test/`: host test harness. `shim/Arduino.h` fakes the core; tests drive
  scripted players through the real `ButtonInput` debounce.
- `display/code.py`: CircuitPython. `HANDLERS` mirrors `Protocol.h` verb for verb.
  `boot.py` makes CIRCUITPY writable by code and read-only to the host. `panel-test.py`
  runs on the host and drives the panel over the REPL.
- `docs/wiring.html` is the wiring reference and the source of the PDF. It is an Artifact
  *fragment* (no `<html>`/`<head>`); `make-print-html.py` wraps it and generates the TOC.
- `hardware/button-board/`: `gen-netlist.py` is the single source of truth for the PCB;
  the schematic and netlist are generated from it, and the `.kicad_pcb` is hand-laid.

## Firmware conventions

- No hardware access in constructors (globals construct before the core is up); all of
  it goes in `Begin()`.
- Static allocation only. Per-player mode instances live in `PlayerModes`.
- Lamps are staged with `Set()` and flushed once per tick (`Game::ShowLamps`). Modes must
  not call `Show()`. Both players share one WS2812 chain, and either one's `Show()`
  flushes it (dirty flag in `Lights.cpp`).
- Adding a game mode means a `MODE_LIST` row plus a class in `Mode.h` (a missing class is
  a compile error) and tests in `test_modes.cpp`. Banners must be ≤5 characters (the
  test enforces it). Every mode with a wrong button must lose points to random mashing;
  `TestMasher` checks this from a large bank, so keep it passing when you tune points.
- Adding a protocol message means adding it to `Protocol.h`, to `HANDLERS` in `code.py`,
  and to `kDisplayTestMessages` in `Debug.cpp`, so the debug DISPLAY screen exercises it.
- `kChasePath` (the order of the caps around the ring) is still unverified on the table.
  Chase and the dance both follow it.
- Pin 8 (pixel data) doubles as the audio shield's I2S input, and `kReservedAudioPins`
  are kept free for a future audio board.

## Display constraints

- The panel shows two rotated text columns, one per player (P1 `DWR` on the left, P2
  `UPR` on the right). Unscrolled text fits **5 characters**: prefix a space, as
  `on_mode` does. Longer text has to scroll.
- `terminalio` cannot fit "BUTTON". The splash title uses its own `TITLE_FONT` in
  `code.py`, covering only the letters it needs.
- `displayio.Bitmap` takes `bitmap[x, y] = v`; calling `__setitem__` explicitly fails on
  the board.
- Target CircuitPython 10 (≥9 works); ruff targets py38 syntax. Skip f-strings in
  `code.py`: `.format()` is the house style there (UP032 ignored).
- There is no way to run `code.py` here. Test it by stubbing `board`, `displayio`,
  `adafruit_display_text` etc. and exec'ing everything above `# --- Main loop`. Render
  frames to PNG when the visuals matter.

## Hardware facts that bite

- Power is a star from an HUSB238 PD trigger (5 V/3 A) fed by a USB power bank. The LED
  panel must be fed from the star, **never through the Portal's screw terminals**: with
  those terminals feeding the panel, the rail sags and the panel shows only red.
- To reflash the Portal, unplug its USB-C power pigtail before connecting a computer.
  Hold UP while powering on to make CIRCUITPY writable.
- `kPixelBrightness` 64 caps all-white at ~1.8 A. Don't raise it without measuring the
  rail on the debug LED ALL screen.
- Debug mode: hold both start buttons for 2 s in attract. A lone start press waits
  `kStartArbitrationMs` so the combo can complete.

## Style

- Comments explain *why*, often citing the bug or measurement behind a choice. Match
  that density. British spelling in prose and comments ("colour"); identifiers use
  `Color`.
- C++: clang-format (LLVM base, 2-space, 100 columns). Python: ruff, 100 columns.
- Commit messages: imperative subject, then a body explaining what changed and why.
- `docs/wiring.html` values are mirrored from `Config.h`. When pins change, update both;
  `make check-pins` catches pin drift.
