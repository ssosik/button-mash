# Whack A Mole Attack -- build and lint targets.
#
# Requires arduino-cli with the Teensy core installed:
#   brew install arduino-cli
#   arduino-cli core install teensy:avr --additional-urls \
#     https://www.pjrc.com/teensy/package_teensy_index.json
#
# Optional lint tools:
#   brew install clang-format llvm ruff
# or, with nothing installed, run them through uv at CI's versions:
#   make lint CLANG_FORMAT="uvx --from clang-format==18.1.8 clang-format" RUFF="uvx ruff"

FQBN    := teensy:avr:teensy41
CLANG_FORMAT ?= clang-format
RUFF    ?= ruff

# Which hardware the firmware is built for. Defaults match Config.h: the
# rebuilt table, one GPIO per button and WS2812 caps. Override on the command
# line for version 1's resistor ladder and plain dome lamps:
#
#     make upload GPIO=0 PIXELS=0
#
GPIO    ?= 1
PIXELS  ?= 1
SKETCH  := firmware/WhackAMole
BUILD   := build
CHROME  := /Applications/Google Chrome.app/Contents/MacOS/Google Chrome
SOURCES := $(wildcard firmware/WhackAMole/*.cpp firmware/WhackAMole/*.h) $(SKETCH)/WhackAMole.ino

.PHONY: all build matrix upload monitor format format-check tidy lint-py lint check-pins stl wiring-pdf test clean

all: build

## Compile for the hardware selected by GPIO= and PIXELS= (see the top of this
## file). The Teensy platform has no build.extra_flags hook, so the base
## build.flags.defs is read back and appended to rather than replaced.
build:
	@defs=`arduino-cli board details -b $(FQBN) --show-properties | sed -n 's/^build\.flags\.defs=//p'`; \
	if [ -z "$$defs" ]; then echo "could not read build.flags.defs for $(FQBN)"; exit 1; fi; \
	echo "building WAM_INPUT_GPIO=$(GPIO) WAM_LIGHTS_PIXELS=$(PIXELS)"; \
	arduino-cli compile --warnings all --fqbn $(FQBN) \
	  --build-property "build.flags.defs=$$defs -DWAM_INPUT_GPIO=$(GPIO) -DWAM_LIGHTS_PIXELS=$(PIXELS)" \
	  --build-path $(BUILD) $(SKETCH)

## Compile every combination of input and lamp hardware. This is what keeps the
## resistor-ladder path from bit-rotting while the GPIO rewire is in progress,
## and vice versa.
##
## The Teensy platform.txt has no build.extra_flags hook -- its recipes only
## interpolate build.flags.defs -- so the base value is read back and appended
## to rather than replaced. Overriding a property the platform does not
## reference is silently ignored, which makes every variant build the default
## config and pass for the wrong reason.
matrix:
	@defs=`arduino-cli board details -b $(FQBN) --show-properties | sed -n 's/^build\.flags\.defs=//p'`; \
	if [ -z "$$defs" ]; then echo "could not read build.flags.defs for $(FQBN)"; exit 1; fi; \
	rc=0; \
	for gpio in 0 1; do \
	  for pixels in 0 1; do \
	    printf 'WAM_INPUT_GPIO=%s WAM_LIGHTS_PIXELS=%s ... ' $$gpio $$pixels; \
	    if arduino-cli compile --clean --warnings all --fqbn $(FQBN) \
	        --build-property "build.flags.defs=$$defs -DWAM_INPUT_GPIO=$$gpio -DWAM_LIGHTS_PIXELS=$$pixels" \
	        $(SKETCH) > /tmp/wam-build.log 2>&1; then \
	      echo OK; \
	    else \
	      echo FAIL; cat /tmp/wam-build.log; rc=1; \
	    fi; \
	  done; \
	done; \
	exit $$rc

## Compile and flash a connected Teensy. Honours GPIO= and PIXELS=.
##
## Uses `compile --upload` rather than a separate `upload --input-dir`: the
## latter hands the Teensy Loader a path it cannot resolve and fails with
## "could not find the file WhackAMole.ino" even with the hex sitting there.
## The port is found rather than assumed -- auto-detection fails with
## "no upload port provided".
##
## If the Teensy's VUSB/VIN pads are cut, USB alone will not power it: the board
## needs its 5 V supply connected to be programmed at all. An unpowered Teensy
## never enumerates and looks unplugged.
upload:
	@defs=`arduino-cli board details -b $(FQBN) --show-properties | sed -n 's/^build\.flags\.defs=//p'`; \
	if [ -z "$$defs" ]; then echo "could not read build.flags.defs for $(FQBN)"; exit 1; fi; \
	port=`arduino-cli board list | awk '/$(subst :,\:,$(FQBN))/ {print $$1; exit}'`; \
	if [ -z "$$port" ]; then \
	  echo "no Teensy found. Powered? (VUSB cut means USB alone will not do it.)"; \
	  echo "A board in bootloader mode still lists, as 'Teensy Ports'."; \
	  exit 1; \
	fi; \
	echo "uploading WAM_INPUT_GPIO=$(GPIO) WAM_LIGHTS_PIXELS=$(PIXELS) to $$port"; \
	arduino-cli compile --fqbn $(FQBN) \
	  --build-property "build.flags.defs=$$defs -DWAM_INPUT_GPIO=$(GPIO) -DWAM_LIGHTS_PIXELS=$(PIXELS)" \
	  --upload -p "$$port" $(SKETCH)

## Watch the firmware's serial output.
##
## Prefers tio when installed, because every upload re-enumerates the Teensy and
## tio reconnects on its own -- arduino-cli monitor drops out and has to be
## restarted after each flash. In tio the escape is ctrl-t: ctrl-t q to quit,
## ctrl-t ? for the rest. Plain ctrl-c is passed through to the board.
monitor:
	@port=`ls /dev/cu.usbmodem* 2>/dev/null | head -1`; \
	if [ -z "$$port" ]; then \
	  echo "no /dev/cu.usbmodem* found."; \
	  echo "The firmware must be running and calling Serial.begin() to enumerate."; \
	  echo "A board sitting in the bootloader presents as HID, not serial."; \
	  exit 1; \
	fi; \
	if command -v tio >/dev/null 2>&1; then \
	  echo "monitoring $$port with tio -- ctrl-t q to quit, reconnects after a flash"; \
	  tio -b 115200 -a latest "$$port"; \
	else \
	  echo "monitoring $$port at 115200 -- ctrl-c to exit"; \
	  arduino-cli monitor -p "$$port" -c baudrate=115200; \
	fi

format:
	$(CLANG_FORMAT) -i $(SOURCES)

format-check:
	$(CLANG_FORMAT) --dry-run --Werror $(SOURCES)

## clang-tidy needs a compile database; arduino-cli emits one into the build dir.
tidy:
	arduino-cli compile --fqbn $(FQBN) --build-path $(BUILD) --only-compilation-database $(SKETCH)
	clang-tidy -p $(BUILD) firmware/WhackAMole/*.cpp

lint-py:
	$(RUFF) check .
	$(RUFF) format --check .

## Fail if the wiring doc's pin table has drifted from Config.h. The doc claims
## to mirror it, and across three remaps it silently did not.
check-pins:
	python3 docs/check-pins.py

lint: format-check lint-py check-pins

## Render the printed parts. Needs OpenSCAD: `brew install --cask openscad@snapshot`
## (the stable cask is currently disabled). The .scad asserts on the measured
## dimensions, so a failed render here means a part that would not fit.
stl:
	mkdir -p $(BUILD)/stl
	openscad -D 'part="seat"' -o $(BUILD)/stl/button-ring-seat.stl hardware/button-led-carrier.scad
	openscad -D 'part="plug"' -o $(BUILD)/stl/button-bore-plug.stl hardware/button-led-carrier.scad

## Render docs/wiring.html to a PDF. Needs Google Chrome.
## Chrome ignores --print-to-pdf-no-header; --no-pdf-header-footer is the flag
## that actually suppresses the date/title/URL stamps.
wiring-pdf:
	python3 docs/make-print-html.py docs/wiring.html $(BUILD)/wiring-print.html
	"$(CHROME)" --headless --disable-gpu --no-sandbox \
	  --virtual-time-budget=12000 --no-pdf-header-footer \
	  --print-to-pdf="$(PWD)/docs/mole-table-wiring.pdf" \
	  "file://$(PWD)/$(BUILD)/wiring-print.html" 2>/dev/null || true
	@test -f docs/mole-table-wiring.pdf && echo "docs/mole-table-wiring.pdf" || \
	  (echo "PDF not produced -- is Chrome at $(CHROME)?" && exit 1)

## Play every game mode on the host, through the real debounce, with scripted
## players. No Teensy needed. Built with AddressSanitizer and UBSan, so an
## out-of-range cap index fails the run instead of quietly corrupting memory.
TEST_SRCS := $(addprefix $(SKETCH)/,Mode.cpp WhackMode.cpp CaptchaMode.cpp ChaseMode.cpp \
               LogicMode.cpp SimonMode.cpp Player.cpp ButtonInput.cpp Lights.cpp \
               Dance.cpp)
test:
	@mkdir -p $(BUILD)
	$(CXX) -std=c++17 -O1 -g -Wall -Wextra -fsanitize=address,undefined \
	  -Ifirmware/test/shim -I$(SKETCH) -DWAM_INPUT_GPIO=1 -DWAM_LIGHTS_PIXELS=0 \
	  firmware/test/test_modes.cpp $(TEST_SRCS) -o $(BUILD)/test_modes
	$(BUILD)/test_modes

clean:
	rm -rf $(BUILD)
