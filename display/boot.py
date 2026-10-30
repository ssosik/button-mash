"""Decide whether CIRCUITPY is writable by the running program.

CircuitPython mounts the filesystem read-only to code.py by default so the host
computer can edit files over USB. The game needs to write highscore.txt, which
means the program side has to own the mount instead.

Hold the UP button while powering on to keep the drive editable from a computer.
Otherwise the game gets write access and the drive appears read-only to the
host, which is what you want for the table in normal use.
"""

import board
import digitalio
import storage

try:
    button = digitalio.DigitalInOut(board.BUTTON_UP)
    button.switch_to_input(pull=digitalio.Pull.UP)
    editing_from_host = not button.value  # pressed reads low
    button.deinit()
except (AttributeError, ValueError):
    # No such button on this board revision; default to the game owning writes.
    editing_from_host = False

if editing_from_host:
    print("boot.py: UP held -- leaving CIRCUITPY writable from USB")
else:
    storage.remount("/", readonly=False)
    print("boot.py: filesystem writable by code.py (highscore will persist)")
