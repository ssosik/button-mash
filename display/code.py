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
import math
import rgbmatrix
import terminalio
import time
from adafruit_display_text import label

# --- Configuration ---------------------------------------------------------

MATRIX_WIDTH = 32
MATRIX_HEIGHT = 32
BAUDRATE = 115200

HIGHSCORE_PATH = "/highscore.txt"

P1_COLOR = 0x33FF55
P2_COLOR = 0xFF99FF

# Frames between scroll steps. Larger is slower.
SCROLL_PERIOD = 125

# Character cell height of terminalio.FONT, used to work out when a vertical
# label has fully left the panel.
CHAR_CELL = 6

# The splash: a spinning pinwheel behind the title, one word at a time. Shown
# from power-on until the Teensy first speaks, and again whenever it asks.
TITLE_WORDS = ("CUB", "SCOUT", "BUTTON", "MASH")
TITLE_WORD_MS = 700  # each word lit
TITLE_GAP_MS = 150  # dark between words
TITLE_REST_MS = 700  # dark after the last word, before it starts again

# The title's own font. terminalio fits five letters to a 32-pixel column and
# BUTTON has six, so these are narrower: 7 rows tall, '#' lit, one column of
# space between letters. Only the letters the title uses are here.
TITLE_FONT = {
    "A": (".##.", "#..#", "#..#", "####", "#..#", "#..#", "#..#"),
    "B": ("###.", "#..#", "#..#", "###.", "#..#", "#..#", "###."),
    "C": (".###", "#...", "#...", "#...", "#...", "#...", ".###"),
    "H": ("#..#", "#..#", "#..#", "####", "#..#", "#..#", "#..#"),
    "M": ("#...#", "##.##", "#.#.#", "#...#", "#...#", "#...#", "#...#"),
    "N": ("#..#", "##.#", "##.#", "#.##", "#.##", "#..#", "#..#"),
    "O": (".##.", "#..#", "#..#", "#..#", "#..#", "#..#", ".##."),
    "S": (".###", "#...", "#...", ".##.", "...#", "...#", "###."),
    "T": ("###", ".#.", ".#.", ".#.", ".#.", ".#.", ".#."),
    "U": ("#..#", "#..#", "#..#", "#..#", "#..#", "#..#", ".##."),
}
TITLE_FONT_HEIGHT = 7

# Left edge of each player's title column, mirrored about the panel's centre
# like the score columns. Each column carries a one-pixel black outline round
# the letters, so it reaches one pixel further either side.
TITLE_P1_X = 5
TITLE_P2_X = MATRIX_WIDTH - TITLE_P1_X - TITLE_FONT_HEIGHT
TITLE_COLUMN_WIDTH = TITLE_FONT_HEIGHT + 2

# The pinwheel. Each pixel belongs to one blade for good; spinning only moves
# the colours round the blades, which costs a palette update rather than a
# redraw of 1,024 pixels.
PINWHEEL_BLADES = 12
PINWHEEL_TWIST = 0.3  # turns of curl from the centre to the corners; 0 for straight blades
PINWHEEL_LEVEL = 0.35  # blade brightness, kept low so the words stay on top
PINWHEEL_STEP_MS = 90  # one blade's turn

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
        with open(HIGHSCORE_PATH) as handle:
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


# --- Splash ----------------------------------------------------------------


def hue_color(hue, level):
    """A fully saturated colour as 0xRRGGBB. `hue` is in turns, 0 to 1."""
    sector = (hue % 1.0) * 6
    i = int(sector)
    f = sector - i
    rising, falling = f, 1 - f
    r, g, b = (
        (1, rising, 0),
        (falling, 1, 0),
        (0, 1, rising),
        (0, falling, 1),
        (rising, 0, 1),
        (1, 0, falling),
    )[i % 6]
    return (int(r * 255 * level) << 16) | (int(g * 255 * level) << 8) | int(b * 255 * level)


def pinwheel_blade(x, y):
    """Which blade the pixel at (x, y) belongs to."""
    dx = x - (MATRIX_WIDTH - 1) / 2
    dy = y - (MATRIX_HEIGHT - 1) / 2
    radius = math.sqrt(dx * dx + dy * dy) / (MATRIX_WIDTH / 2)
    turn = math.atan2(dy, dx) / (2 * math.pi) + PINWHEEL_TWIST * radius
    return int((turn % 1.0) * PINWHEEL_BLADES) % PINWHEEL_BLADES


def pinwheel_colors():
    """One colour per blade, the rainbow once round."""
    return [hue_color(i / PINWHEEL_BLADES, PINWHEEL_LEVEL) for i in range(PINWHEEL_BLADES)]


def title_pixels(word):
    """The lit pixels of `word` laid flat, as (along, row) pairs, and its length.

    `along` runs in reading order from the first letter; `row` 0 is the top of
    the letters.
    """
    lit = []
    along = 0
    for letter in word:
        glyph = TITLE_FONT[letter]
        for row, line in enumerate(glyph):
            for col, cell in enumerate(line):
                if cell == "#":
                    lit.append((along + col, row))
        along += len(glyph[0]) + 1
    return lit, along - 1


# Title column bitmap values: see-through, letter, and the outline round it.
CLEAR, LETTER, OUTLINE = 0, 1, 2


def draw_title_word(p1_bitmap, p2_bitmap, word):
    """Draw `word` into both title columns, centred along each and outlined.

    Turned the same way as the score columns: P1's reads downward with the tops
    of the letters toward the panel's right edge, P2's reads upward with them
    toward the left, so each player sees it upright from their own side.
    """
    p1_bitmap.fill(CLEAR)
    p2_bitmap.fill(CLEAR)
    if not word:
        return
    lit, length = title_pixels(word)
    start = (MATRIX_HEIGHT - length) // 2
    last_row = TITLE_FONT_HEIGHT - 1
    # Column-local coordinates, one pixel in from the edge to leave room for
    # the outline.
    p1 = set((1 + last_row - row, start + along) for along, row in lit)
    p2 = set((1 + row, MATRIX_HEIGHT - 1 - (start + along)) for along, row in lit)
    for bitmap, letters in ((p1_bitmap, p1), (p2_bitmap, p2)):
        for x, y in letters:
            for nx in (x - 1, x, x + 1):
                for ny in (y - 1, y, y + 1):
                    inside = 0 <= nx < TITLE_COLUMN_WIDTH and 0 <= ny < MATRIX_HEIGHT
                    if inside and (nx, ny) not in letters:
                        bitmap[nx, ny] = OUTLINE
        for x, y in letters:
            bitmap[x, y] = LETTER


def title_frames():
    """The title as (word, ms) pairs; a word of None is a dark pause."""
    frames = []
    for word in TITLE_WORDS:
        frames.append((word, TITLE_WORD_MS))
        frames.append((None, TITLE_GAP_MS))
    frames[-1] = (None, TITLE_REST_MS)
    return frames


# --- Scenes ----------------------------------------------------------------


class Scenes:
    """What this panel can show: the splash, and the players' text."""

    def __init__(self):
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

        self.splash = displayio.Group()

        wheel = displayio.Bitmap(MATRIX_WIDTH, MATRIX_HEIGHT, PINWHEEL_BLADES)
        for y in range(MATRIX_HEIGHT):
            for x in range(MATRIX_WIDTH):
                wheel[x, y] = pinwheel_blade(x, y)
        self.wheel_colors = pinwheel_colors()
        self.wheel_palette = displayio.Palette(PINWHEEL_BLADES)
        self.wheel_turn = 0
        self.wheel_since = 0
        self._paint_wheel()
        self.splash.append(displayio.TileGrid(wheel, pixel_shader=self.wheel_palette))

        self.title_bitmaps = []
        for x, color in ((TITLE_P1_X - 1, P1_COLOR), (TITLE_P2_X - 1, P2_COLOR)):
            bitmap = displayio.Bitmap(TITLE_COLUMN_WIDTH, MATRIX_HEIGHT, 3)
            palette = displayio.Palette(3)
            palette[CLEAR] = 0x000000
            palette[LETTER] = color
            palette[OUTLINE] = 0x000000
            palette.make_transparent(CLEAR)
            self.splash.append(displayio.TileGrid(bitmap, pixel_shader=palette, x=x))
            self.title_bitmaps.append(bitmap)
        self.title_frames = title_frames()
        self.title_index = 0
        self.title_since = 0

        self.showing_splash = False
        self.scrolling = True
        self.frame = 0

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
        if showing:
            # From the first word each time, so it always reads as a title.
            self.title_index = 0
            self.title_since = self.wheel_since = time.monotonic_ns() // 1000000
            self._draw_title_frame()
        display.root_group = self.splash if showing else self.players

    def _paint_wheel(self):
        count = PINWHEEL_BLADES
        for blade in range(count):
            self.wheel_palette[blade] = self.wheel_colors[(blade + self.wheel_turn) % count]

    def _draw_title_frame(self):
        word, _ = self.title_frames[self.title_index]
        draw_title_word(self.title_bitmaps[0], self.title_bitmaps[1], word)

    def _tick_splash(self):
        now = time.monotonic_ns() // 1000000
        if now - self.wheel_since >= PINWHEEL_STEP_MS:
            self.wheel_since = now
            self.wheel_turn = (self.wheel_turn + 1) % PINWHEEL_BLADES
            self._paint_wheel()

        _, hold = self.title_frames[self.title_index]
        if now - self.title_since < hold:
            return
        self.title_since = now
        self.title_index = (self.title_index + 1) % len(self.title_frames)
        self._draw_title_frame()

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
            self._tick_splash()
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

    scenes.show_splash(False)
    scenes.set_text("{:>6d}".format(p1_score), "{:>6d}".format(p2_score), scrolling=False)


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


def _parse_color(token):
    """Six hex digits, or '-' when the player has nothing to find."""
    if token == b"-":
        return None
    try:
        return int(token.decode("utf-8"), 16)
    except ValueError:
        return None


def on_target(scenes, args):
    """#TARGET:<p1>:<p2> -- each player's score turns the colour they must find.

    Recolouring the score rather than drawing a swatch needs no layout on a
    32x32 panel that already holds two columns of rotated text.
    """
    parts = args.split(b":")
    if len(parts) != 2:
        return
    scenes.set_colors(_parse_color(parts[0]), _parse_color(parts[1]))


# The most characters a column shows without scrolling; see on_mode.
STILL_TEXT_MAX = 5


def on_debug(scenes, args):
    """#DEBUG:<banner> -- lets the table be tested without a laptop attached.

    A banner short enough to fit, like the button screen's "P1 B3", is shown
    still so it can be read at a glance; a longer one scrolls.
    """
    text = args.decode("utf-8", "replace")
    if len(text) <= STILL_TEXT_MAX:
        _both(scenes, " " + text, scrolling=False)
    else:
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

    # The splash holds only until the Teensy says something else -- including
    # at power-on, before it has asked for the splash at all.
    if scenes.showing_splash and verb != b"#SHOWSPLASH":
        scenes.show_splash(False)

    if verb not in KEEPS_TARGET_COLORS:
        scenes.set_colors()

    if verb == b"#GAMEREADY":
        handler = COUNTDOWN.get(args)
        if handler is not None:
            handler(scenes, args)
        return

    handler = HANDLERS.get(verb)
    if handler is None:
        print("unknown message: {}".format(line))
        scenes.set_text("unknown: {}     ".format(line), "unknown: {}     ".format(line))
        return

    handler(scenes, args)


# --- Main loop -------------------------------------------------------------

uart = busio.UART(board.TX, board.RX, baudrate=BAUDRATE, timeout=0)
state = {"highscore": load_highscore()}
scenes = Scenes()
scenes.show_splash(True)

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
