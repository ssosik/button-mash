"""Whack A Mole Attack -- Matrix Portal S3 display.

This board renders only. All game logic lives on the Teensy, which sends
newline-terminated messages over the UART; see firmware/WhackAMole/Protocol.h.

Framing matters here. The previous version called uart.read(32) and tested the
raw chunk with startswith(), so any message that happened to straddle a 32-byte
read boundary was silently dropped or misparsed. Bytes are now accumulated in a
buffer and dispatched only once a complete '\\n'-terminated line has arrived.
"""

import board
import busio
import displayio
import framebufferio
import rgbmatrix
import terminalio
from adafruit_display_text import label

# --- Configuration ---------------------------------------------------------

MATRIX_WIDTH = 32
MATRIX_HEIGHT = 32
BAUDRATE = 115200

HIGHSCORE_PATH = "/highscore.txt"
SPLASH_BITMAP = "running-monty-mole.bmp"

P1_COLOR = 0x33FF55
P2_COLOR = 0xFF99FF

# Frames between scroll steps. Larger is slower.
SCROLL_PERIOD = 125

# Character cell height of terminalio.FONT, used to work out when a vertical
# label has fully left the panel.
CHAR_CELL = 6

SPLASH_LEFT_LIMIT = -55

# --- Panel setup -----------------------------------------------------------

displayio.release_displays()
matrix = rgbmatrix.RGBMatrix(
    width=MATRIX_WIDTH,
    bit_depth=4,
    rgb_pins=[
        board.MTX_R1,
        board.MTX_G1,
        board.MTX_B1,
        board.MTX_R2,
        board.MTX_G2,
        board.MTX_B2,
    ],
    addr_pins=[board.MTX_ADDRA, board.MTX_ADDRB, board.MTX_ADDRC, board.MTX_ADDRD],
    clock_pin=board.MTX_CLK,
    latch_pin=board.MTX_LAT,
    output_enable_pin=board.MTX_OE,
)
display = framebufferio.FramebufferDisplay(matrix, rotation=0, auto_refresh=False)


# --- High score ------------------------------------------------------------


def load_highscore():
    """Read the saved high score, or 0 if there isn't a usable one.

    Returns an int. The previous version returned the raw line from the file,
    so after a reboot every `score > highscore` comparison raised TypeError
    comparing int to str.
    """
    try:
        with open(HIGHSCORE_PATH, "r") as handle:
            return int(handle.readline().strip())
    except (OSError, ValueError):
        return 0


def save_highscore(score):
    """Persist a new high score, if the filesystem happens to be writable.

    CIRCUITPY is read-only to the running program unless boot.py has remounted
    it; see boot.py. A read-only filesystem is not an error worth crashing the
    game over, so the score simply stays in RAM for this session.
    """
    try:
        with open(HIGHSCORE_PATH, "w") as handle:
            handle.write("{}\n".format(score))
        return True
    except OSError:
        print("highscore not saved: filesystem is read-only (see boot.py)")
        return False


# --- Scenes ----------------------------------------------------------------


class Scenes:
    """The two things this panel can show: the attract splash, and the score."""

    def __init__(self):
        odb = displayio.OnDiskBitmap(SPLASH_BITMAP)
        self.mole = displayio.TileGrid(odb, pixel_shader=odb.pixel_shader)
        self.splash = displayio.Group()
        self.splash.append(self.mole)

        self.p1 = label.Label(
            text="",
            font=terminalio.FONT,
            color=P1_COLOR,
            line_spacing=0.7,
            scale=1,
            label_direction="DWR",
        )
        self.p2 = label.Label(
            text="",
            font=terminalio.FONT,
            color=P2_COLOR,
            line_spacing=0.7,
            scale=1,
            label_direction="UPR",
        )

        self.players = displayio.Group()
        self.players.append(self.p1)
        self.players.append(self.p2)

        self.showing_splash = False
        self.scrolling = True
        self.frame = 0

        # Captcha's Stroop words, per player. While one is up it holds that
        # player's column and the score waits in score_text until it goes.
        self.words = [None, None]
        self.score_text = ["", ""]

        self.reset_positions()
        display.root_group = self.players

    def reset_positions(self):
        self.p1.x = 8
        self.p1.y = -4
        self.p2.x = 24
        self.p2.y = MATRIX_HEIGHT + 4

    def set_text(self, p1_text=None, p2_text=None, scrolling=True):
        if p1_text is not None:
            self.p1.text = p1_text
        if p2_text is not None:
            self.p2.text = p2_text
        self.scrolling = scrolling
        if not scrolling:
            self.reset_positions()

    def set_colors(self, p1_color=None, p2_color=None):
        """Recolour each player's text. None restores that player's own colour."""
        self.p1.color = P1_COLOR if p1_color is None else p1_color
        self.p2.color = P2_COLOR if p2_color is None else p2_color

    def show_splash(self, showing):
        if showing == self.showing_splash:
            return
        self.showing_splash = showing
        display.root_group = self.splash if showing else self.players

    def _scroll_down(self, line):
        line.y -= 1
        if line.y < -(len(line.text) * CHAR_CELL):
            line.y = MATRIX_HEIGHT

    def _scroll_up(self, line):
        line.y += 1
        if line.y >= len(line.text) * CHAR_CELL:
            line.y = -line.bounding_box[2]

    def tick(self):
        if self.showing_splash:
            self.mole.x -= 1
            if self.mole.x < SPLASH_LEFT_LIMIT:
                self.mole.x = MATRIX_WIDTH
            return

        if not self.scrolling:
            return

        self.frame += 1
        if self.frame < SCROLL_PERIOD:
            return
        self.frame = 0
        self._scroll_down(self.p1)
        self._scroll_up(self.p2)


# --- Message handlers ------------------------------------------------------
#
# One entry per verb in Protocol.h. Each takes (scenes, args) where args is
# whatever followed the first ':', as bytes.


def _both(scenes, text, scrolling=True):
    scenes.show_splash(False)
    scenes.set_text(text, text, scrolling=scrolling)


def on_conready(scenes, args):
    uart.write(b"#DSPREADY\n")
    scenes.show_splash(False)


def on_newgame(scenes, args):
    _both(scenes, "New Game       ")


def on_showsplash(scenes, args):
    scenes.scrolling = False
    scenes.show_splash(True)


def on_showpressstart(scenes, args):
    _both(scenes, "Press Start      ")


def on_showhighscore(scenes, args):
    _both(scenes, "Highscore: {}      ".format(state["highscore"]))


def on_isp1ready(scenes, args):
    scenes.show_splash(False)
    scenes.set_text(p2_text="Waiting          ")


def on_isp2ready(scenes, args):
    scenes.show_splash(False)
    scenes.set_text(p1_text="Waiting          ")


def on_ready(scenes, args):
    _both(scenes, " READY ", scrolling=False)


def on_set(scenes, args):
    _both(scenes, "  SET ", scrolling=False)


def on_go(scenes, args):
    _both(scenes, "  GO! ", scrolling=False)


def _show_columns(scenes):
    """Each player's column: their Stroop word if one is up, else their score."""
    p1, p2 = (
        " " + word if word else score
        for word, score in zip(scenes.words, scenes.score_text)
    )
    scenes.show_splash(False)
    scenes.set_text(p1, p2, scrolling=False)


def on_score(scenes, args):
    """#SCORE:<p1>:<p2>"""
    parts = args.split(b":")
    if len(parts) != 2:
        return
    try:
        p1_score = int(parts[0])
        p2_score = int(parts[1])
    except ValueError:
        return

    scenes.score_text = ["{:>6d}".format(p1_score), "{:>6d}".format(p2_score)]
    _show_columns(scenes)


def _win(scenes, args, winner):
    try:
        score = int(args)
    except ValueError:
        return

    scenes.show_splash(False)

    if score > state["highscore"]:
        state["highscore"] = score
        save_highscore(score)
        text = "WINNER! NEW HIGHSCORE! {}     ".format(score)
    else:
        text = "YOU WIN {}      ".format(score)

    if winner == 1:
        scenes.set_text(text, "Press Start      ")
    else:
        scenes.set_text("Press Start      ", text)


def on_player1win(scenes, args):
    _win(scenes, args, 1)


def on_player2win(scenes, args):
    _win(scenes, args, 2)


def on_tiegame(scenes, args):
    try:
        score = int(args)
    except ValueError:
        return
    if score > state["highscore"]:
        state["highscore"] = score
        save_highscore(score)
    _both(scenes, "TIE GAME {}      ".format(score))


def on_mode(scenes, args):
    """#MODE:<banner> -- names the next part of the medley.

    Unscrolled, like READY / SET / GO, so the banner must fit in five characters;
    the leading space covers the first cell, which sits partly off the panel.
    """
    _both(scenes, " {}".format(args.decode("utf-8", "replace")), scrolling=False)


def _parse_target(token):
    """'RRGGBB', 'RRGGBB,WORD', or '-' when the player has nothing to find.

    Returns (colour or None, word or None).
    """
    color, _, word = token.partition(b",")
    if color == b"-":
        return None, None
    try:
        color = int(color.decode("utf-8"), 16)
    except ValueError:
        return None, None
    return color, (word.decode("utf-8", "replace") or None)


def on_target(scenes, args):
    """#TARGET:<p1>:<p2> -- each player's score turns the colour they must find.

    Recolouring the score rather than drawing a swatch needs no layout on a
    32x32 panel that already holds two columns of rotated text. In Captcha's
    Stroop rounds a word takes the score's place, drawn in the colour to find
    and naming a different one.
    """
    parts = args.split(b":")
    if len(parts) != 2:
        return
    (p1_color, p1_word), (p2_color, p2_word) = (_parse_target(p) for p in parts)
    scenes.set_colors(p1_color, p2_color)
    words = [p1_word, p2_word]
    if words != scenes.words:
        scenes.words = words
        _show_columns(scenes)


def on_debug(scenes, args):
    """#DEBUG:<banner> -- lets the table be tested without a laptop attached."""
    text = args.decode("utf-8", "replace")
    _both(scenes, "{}      ".format(text))


HANDLERS = {
    b"#CONREADY": on_conready,
    b"#NEWGAME": on_newgame,
    b"#SHOWSPLASH": on_showsplash,
    b"#SHOWPRESSSTART": on_showpressstart,
    b"#SHOWHIGHSCORE": on_showhighscore,
    b"#ISP1READY": on_isp1ready,
    b"#ISP2READY": on_isp2ready,
    b"#GAMEREADY": None,  # dispatched on the argument, see handle_line
    b"#SCORE": on_score,
    b"#PLAYER1WIN": on_player1win,
    b"#PLAYER2WIN": on_player2win,
    b"#TIEGAME": on_tiegame,
    b"#DEBUG": on_debug,
    b"#MODE": on_mode,
    b"#TARGET": on_target,
}

# Messages that leave the colours #TARGET set alone. Anything else is a new
# screen, and a target colour carried over from the last mode would paint the
# winner's banner, say, in the colour of a captcha prompt.
KEEPS_TARGET_COLORS = (b"#SCORE", b"#TARGET")

COUNTDOWN = {b"READY": on_ready, b"SET": on_set, b"GO": on_go}


def handle_line(scenes, line):
    line = line.strip()
    if not line:
        return

    verb, _, args = line.partition(b":")

    if verb not in KEEPS_TARGET_COLORS:
        scenes.set_colors()
        scenes.words = [None, None]

    if verb == b"#GAMEREADY":
        handler = COUNTDOWN.get(args)
        if handler is not None:
            handler(scenes, args)
        return

    handler = HANDLERS.get(verb)
    if handler is None:
        print("unknown message: {}".format(line))
        scenes.set_text(
            "unknown: {}     ".format(line), "unknown: {}     ".format(line)
        )
        return

    handler(scenes, args)


# --- Main loop -------------------------------------------------------------

uart = busio.UART(board.TX, board.RX, baudrate=BAUDRATE, timeout=0)
state = {"highscore": load_highscore()}
scenes = Scenes()
scenes.set_text("Whack A Mole Attack      ", "Whack A Mole Attack      ")

rx_buffer = b""

while True:
    data = uart.read(64)
    if data:
        rx_buffer += data
        # Dispatch only complete lines; whatever follows the last newline stays
        # buffered for the next read.
        while b"\n" in rx_buffer:
            line, _, rx_buffer = rx_buffer.partition(b"\n")
            handle_line(scenes, line)

        # A sender that goes quiet mid-line must not grow the buffer forever.
        if len(rx_buffer) > 128:
            rx_buffer = b""

    scenes.tick()
    display.refresh(minimum_frames_per_second=0)
