#!/usr/bin/env python3
"""Drive the LED panel directly from the host, one pattern at a time.

Runs on your computer, not on the board -- it talks to the MatrixPortal's
CircuitPython REPL over USB serial. The point is to close the loop: the
terminal names the pattern and then waits for you, so what is on the panel and
what is on the screen can never drift out of step.

Each step says what you should see and what a deviation means, so a wrong
result identifies the fault on the spot instead of after a round trip.

    python3 display/panel-test.py              # step through everything
    python3 display/panel-test.py --hold green # hold one pattern, hands free
    python3 display/panel-test.py --list       # names for --hold / --only

Interrupts code.py while it runs and soft-reboots the board on exit, so the
game comes back by itself. Nothing is written to CIRCUITPY.
"""

import argparse
import glob
import os
import select
import sys
import time
import tty

PROMPT = b">>> "
PASTE_BANNER = b"paste mode"


# --- talking to the REPL ----------------------------------------------------
#
# Everything here is synchronised on the prompt rather than on sleeps. Fixed
# delays are what make this kind of script flaky: too short and lines get eaten,
# too long and a fifteen-step sweep takes a minute of dead air.
class Repl:
    def __init__(self, port):
        self.fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        tty.setraw(self.fd)
        self.port = port

    def _read_until(self, marker, timeout, anywhere=False):
        """Read until `marker` shows up.

        `anywhere` matters for banners rather than prompts: the paste-mode
        notice is immediately followed by its own "=== " prompt, so waiting for
        the buffer to *end* with the banner waits forever.
        """
        buf = b""
        deadline = time.time() + timeout
        while time.time() < deadline:
            ready, _, _ = select.select([self.fd], [], [], 0.05)
            if ready:
                try:
                    chunk = os.read(self.fd, 4096)
                except (BlockingIOError, OSError):
                    continue
                if chunk:
                    buf += chunk
                    if not marker:
                        continue
                    if marker in buf if anywhere else buf.rstrip().endswith(marker.rstrip()):
                        return buf, True
        return buf, False

    def _write(self, data):
        os.write(self.fd, data)

    def drain(self, quiet_for=0.25):
        """Read until the board has been silent for a moment."""
        buf = b""
        while True:
            ready, _, _ = select.select([self.fd], [], [], quiet_for)
            if not ready:
                return buf
            try:
                buf += os.read(self.fd, 4096)
            except (BlockingIOError, OSError):
                return buf

    def interrupt(self):
        """Stop whatever is running and get a clean prompt.

        The first character typed after an interrupt is routinely swallowed
        while the REPL prints its banner, which silently corrupts the next
        line. Sending a bare newline absorbs that, then we wait for a real
        prompt instead of assuming one arrived.
        """
        for _ in range(3):
            self._write(b"\x03")
            time.sleep(0.25)
        self.drain()
        for _ in range(2):
            self._write(b"\r\n")
            self.drain(0.3)
        self._write(b"\r\n")
        _, ok = self._read_until(PROMPT, 3.0)
        return ok

    def run(self, lines, timeout=8.0):
        """Send one-liners, one at a time, each synchronised on the prompt."""
        if isinstance(lines, str):
            lines = [lines]
        out = ""
        for line in lines:
            self._write(line.encode() + b"\r\n")
            buf, ok = self._read_until(PROMPT, timeout)
            text = buf.decode("utf-8", "replace")
            out += text
            if "Traceback" in text or "Error" in text:
                raise ReplError(line, text)
            if not ok:
                raise ReplError(line, "timed out waiting for a prompt")
        return out

    def paste(self, block, timeout=15.0):
        """Send a multi-line block through paste mode.

        Pasting a `def` line by line puts the REPL into its continuation
        prompt, where every following line is swallowed into the block and
        nothing runs. Paste mode (Ctrl-E ... Ctrl-D) is the only reliable way
        to send indented code.
        """
        self._write(b"\x05")
        _, ok = self._read_until(PASTE_BANNER, 3.0, anywhere=True)
        if not ok:
            raise ReplError("<paste mode>", "board never entered paste mode")
        self._write(block.replace("\n", "\r\n").encode())
        self._write(b"\x04")
        buf, ok = self._read_until(PROMPT, timeout)
        text = buf.decode("utf-8", "replace")
        if "Traceback" in text or "Error" in text:
            raise ReplError("<paste block>", text)
        return text

    def reboot(self):
        """Ctrl-D: soft reboot, which puts code.py back in charge."""
        self._write(b"\x04")
        time.sleep(0.4)

    def close(self):
        os.close(self.fd)


class ReplError(RuntimeError):
    def __init__(self, line, detail):
        super().__init__("while sending %r:\n%s" % (line, detail.strip()))


# --- board-side setup -------------------------------------------------------

SETUP = """
import displayio, rgbmatrix, framebufferio, board
displayio.release_displays()
m = rgbmatrix.RGBMatrix(
    width=%(width)d, bit_depth=%(depth)d,
    rgb_pins=[board.MTX_R1, board.MTX_G1, board.MTX_B1,
              board.MTX_R2, board.MTX_G2, board.MTX_B2],
    addr_pins=[board.MTX_ADDRA, board.MTX_ADDRB, board.MTX_ADDRC, board.MTX_ADDRD],
    clock_pin=board.MTX_CLK, latch_pin=board.MTX_LAT,
    output_enable_pin=board.MTX_OE)
d = framebufferio.FramebufferDisplay(m, auto_refresh=True)
W = m.width
H = m.height
b = displayio.Bitmap(W, H, 2)
p = displayio.Palette(2)
p[0] = 0x000000
p[1] = 0xFFFFFF
g = displayio.Group()
g.append(displayio.TileGrid(b, pixel_shader=p))
d.root_group = g

def box(x0, y0, x1, y1, c=1):
    for y in range(y0, y1):
        for x in range(x0, x1):
            b[x, y] = c

def only(x0, y0, x1, y1):
    b.fill(0)
    box(x0, y0, x1, y1, 1)

def solid(rgb):
    p[1] = rgb
    b.fill(1)

print("SETUP-OK", W, H)
"""


# --- the patterns -----------------------------------------------------------
#
# Ordered so the cheap, unambiguous answers come first: control, then which
# colour channels work at a current too low for the supply to matter, then the
# same at full current, then geometry.

ANSI = {
    "red": "\033[91m", "green": "\033[92m", "blue": "\033[94m",
    "white": "\033[97m", "grey": "\033[90m", "off": "\033[90m",
}
RESET = "\033[0m"


def tests(width, height):
    w, h = width, height
    mid = h // 2
    return [
        dict(key="off", colour="off", title="ALL OFF",
             expect="every LED dark",
             means="Still lit means nothing we send reaches the panel at all -- "
                   "suspect the HUB75 seating, not software.",
             code=["solid(0xFFFFFF)", "b.fill(0)"]),

        dict(key="dim-red", colour="red", title="DIM RED, whole panel",
             expect="even dim red, no banding",
             means="Current here is tiny, so a fault at this step is NOT power.",
             code=["solid(0x200000)"]),
        dict(key="dim-green", colour="green", title="DIM GREEN, whole panel",
             expect="even dim green",
             means="Red worked but green does not => green data line or a rail "
                   "too low for green's ~3.0 V forward drop.",
             code=["solid(0x002000)"]),
        dict(key="dim-blue", colour="blue", title="DIM BLUE, whole panel",
             expect="even dim blue",
             means="Same as green: data line, or a sagging rail.",
             code=["solid(0x000020)"]),

        dict(key="red", colour="red", title="FULL RED, whole panel",
             expect="bright even red",
             means="Dim red fine but full red banded => supply sags under load.",
             code=["solid(0xFF0000)"]),
        dict(key="green", colour="green", title="FULL GREEN, whole panel",
             expect="bright even green",
             means="Green absent at every brightness is a dead G1/G2 pin.",
             code=["solid(0x00FF00)"]),
        dict(key="blue", colour="blue", title="FULL BLUE, whole panel",
             expect="bright even blue",
             means="Blue absent at every brightness is a dead B1/B2 pin.",
             code=["solid(0x0000FF)"]),
        dict(key="white", colour="white", title="FULL WHITE -- maximum current",
             expect="bright even white",
             means="Red-only here while dim white was fine is a classic brownout.",
             code=["solid(0xFFFFFF)"]),

        dict(key="top", colour="white", title="TOP half only",
             expect="rows 0-%d lit, bottom dark" % (mid - 1),
             means="Drives R1/G1/B1. Dark top but working bottom isolates that trio.",
             code=["solid(0xFFFFFF)", "only(0, 0, %d, %d)" % (w, mid)]),
        dict(key="bottom", colour="white", title="BOTTOM half only",
             expect="rows %d-%d lit, top dark" % (mid, h - 1),
             means="Drives R2/G2/B2. Both halves wrong together is an address line.",
             code=["only(0, %d, %d, %d)" % (mid, w, h)]),

        dict(key="row0", colour="white", title="ONE ROW at the very top",
             expect="a single clean line on the top edge",
             means="Several lines, or a line in the wrong place, is a bad address pin.",
             code=["only(0, 0, %d, 1)" % w]),
        dict(key="col0", colour="white", title="ONE COLUMN down the left edge",
             expect="a single clean line on the left edge",
             means="A diagonal instead of a vertical means the configured width "
                   "does not match the panel -- data is wrapping.",
             code=["only(0, 0, 1, %d)" % h]),
        dict(key="border", colour="white", title="1px BORDER on all four edges",
             expect="a clean rectangle framing the whole panel",
             means="Shows the panel's true extent. A border that stops short, or "
                   "wraps, means the width or height is wrong.",
             code=["b.fill(0)",
                   "box(0, 0, %d, 1)" % w,
                   "box(0, %d, %d, %d)" % (h - 1, w, h),
                   "box(0, 0, 1, %d)" % h,
                   "box(%d, 0, %d, %d)" % (w - 1, w, h)]),
        dict(key="corners", colour="white", title="8x8 blocks in TOP-LEFT and BOTTOM-RIGHT",
             expect="exactly two blocks, in opposite corners",
             means="More than two blocks means the image is repeating -- the "
                   "panel is wider or taller than configured.",
             code=["b.fill(0)", "box(0, 0, 8, 8)",
                   "box(%d, %d, %d, %d)" % (w - 8, h - 8, w, h)]),
    ]


# --- driving ----------------------------------------------------------------

def find_port(explicit):
    if explicit:
        return explicit
    for pattern in ("/dev/cu.usbmodem*", "/dev/ttyACM*"):
        found = sorted(glob.glob(pattern))
        if found:
            return found[0]
    sys.exit("No board found. Plug the MatrixPortal in, or pass --port.")


def banner(t):
    colour = ANSI.get(t["colour"], "")
    print("\n%s%s  %s%s" % (colour, "=" * 4, t["title"], RESET))
    print("   expect: %s" % t["expect"])


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", help="serial device (default: first usbmodem)")
    ap.add_argument("--width", type=int, default=32, help="panel width (default 32)")
    ap.add_argument("--depth", type=int, default=4, help="bit depth (default 4)")
    ap.add_argument("--hold", metavar="NAME", help="show one pattern and stay there")
    ap.add_argument("--only", metavar="NAMES", help="comma-separated subset to run")
    ap.add_argument("--delay", type=float, help="auto-advance seconds instead of waiting")
    ap.add_argument("--list", action="store_true", help="list pattern names")
    args = ap.parse_args()

    if args.list:
        for t in tests(args.width, args.width):
            print("  %-10s %s" % (t["key"], t["title"]))
        return

    port = find_port(args.port)
    print("port: %s" % port)
    repl = Repl(port)
    notes = []
    try:
        if not repl.interrupt():
            print("warning: no clean prompt; carrying on anyway", file=sys.stderr)
        out = repl.paste(SETUP % dict(width=args.width, depth=args.depth))
        line = [ln for ln in out.splitlines() if ln.startswith("SETUP-OK")]
        if not line:
            sys.exit("setup did not report back:\n%s" % out.strip())
        _, w, h = line[0].split()
        w, h = int(w), int(h)
        print("matrix built: %d x %d, bit_depth=%d" % (w, h, args.depth))
        if w != args.width:
            print("note: driver reports width %d" % w)

        all_tests = tests(w, h)
        by_key = {t["key"]: t for t in all_tests}

        if args.hold:
            t = by_key.get(args.hold)
            if not t:
                sys.exit("unknown pattern %r (try --list)" % args.hold)
            repl.run(t["code"])
            banner(t)
            print("\n   Holding. Reseat connectors, wiggle the ribbon, measure the")
            print("   panel's power terminals. Ctrl-C here when you are done.")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print()
            return

        chosen = all_tests
        if args.only:
            want = [k.strip() for k in args.only.split(",")]
            missing = [k for k in want if k not in by_key]
            if missing:
                sys.exit("unknown pattern(s): %s (try --list)" % ", ".join(missing))
            chosen = [by_key[k] for k in want]

        print("\nEnter = looked right.  Anything else = what you actually saw.\n"
              "Ctrl-C stops and still prints the summary.")
        for t in chosen:
            repl.run(t["code"])
            banner(t)
            if args.delay:
                time.sleep(args.delay)
                continue
            try:
                said = input("   > ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if said:
                notes.append((t, said))
                print("   if wrong: %s" % t["means"])
    except ReplError as exc:
        print("\nREPL error: %s" % exc, file=sys.stderr)
    finally:
        try:
            repl.run(["b.fill(0)"])
        except Exception:
            pass
        repl.reboot()
        repl.close()

    print("\n" + "=" * 62)
    if not notes:
        print("Every pattern looked right. The panel, its supply and the HUB75")
        print("wiring are all good -- the fault is in what code.py draws.")
    else:
        print("Paste this back:\n")
        for t, said in notes:
            print("  %-10s %s" % (t["key"], t["title"]))
            print("      saw:     %s" % said)
            print("      expect:  %s" % t["expect"])
            print("      meaning: %s" % t["means"])
            print()
    print("Board soft-rebooted; code.py is running again.")


if __name__ == "__main__":
    main()
