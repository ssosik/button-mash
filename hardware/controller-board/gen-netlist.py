#!/usr/bin/env python3
"""The controller board's netlist: one description the schematic and the PCB
are both generated from, so the two cannot disagree.

It is the stripboard in docs/wiring.html, made as a PCB: a socketed Teensy
4.1, a 74AHCT125 lifting the pixel data to 5 V, the 14-way header for the
harness to the button board, a 3-pin JST-XH serial link to the Matrix Portal,
and a screw terminal for 5 V in from the star.

Nothing here is written down twice. The harness positions come from the
button board's own generator, so both ends of the harness agree by
construction, and the switch pins come from Config.h, so a firmware pin change
that the board does not follow fails here instead of on the table.

    python3 hardware/controller-board/gen-netlist.py    # readable net table
"""

import importlib.util
import pathlib
import sys
from collections import defaultdict

HERE = pathlib.Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "button_netlist", HERE.parent / "button-board" / "gen-netlist.py"
)
BB = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(BB)

# The Teensy 4.1's two outer pin rows, top view, USB end first. Pads are
# numbered 1-24 down the left row and 25-48 down the right, so pad numbers
# read the way the board is held rather than anticlockwise like a DIP.
TEENSY_LEFT = [
    "GND",
    "0",
    "1",
    "2",
    "3",
    "4",
    "5",
    "6",
    "7",
    "8",
    "9",
    "10",
    "11",
    "12",
    "3V3",
    "24",
    "25",
    "26",
    "27",
    "28",
    "29",
    "30",
    "31",
    "32",
]
TEENSY_RIGHT = [
    "VIN",
    "GND",
    "3V3",
    "23",
    "22",
    "21",
    "20",
    "19",
    "18",
    "17",
    "16",
    "15",
    "14",
    "13",
    "GND",
    "41",
    "40",
    "39",
    "38",
    "37",
    "36",
    "35",
    "34",
    "33",
]
TEENSY_PINS = TEENSY_LEFT + TEENSY_RIGHT


def teensy_pad(label, nth=0):
    """Pad number of a Teensy pin by its silkscreen label (nth for GND, 3V3)."""
    pads = [i + 1 for i, name in enumerate(TEENSY_PINS) if name == str(label)]
    return pads[nth]


PIXEL_PIN = 8  # kPixelDataPin; Serial2 TX, which WS2812Serial drives
SERIAL_RX, SERIAL_TX = 0, 1  # Serial1, to the Matrix Portal

FP_TEENSY = "controller-board:Teensy41_Socketed"
FP_SHIFTER = "Package_DIP:DIP-14_W7.62mm_Socket"
FP_HARNESS = "Connector_PinHeader_2.54mm:PinHeader_1x14_P2.54mm_Vertical"
FP_SERIAL = "Connector_JST:JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical"
# A screw terminal, as on the button board: nothing else on this board is
# 2-pin, but there is no reason to let a power lead be pluggable anywhere.
FP_PWR = "TerminalBlock:TerminalBlock_MaiXu_MX126-5.0-02P_1x02_P5.00mm"
FP_BULK = "Capacitor_THT:CP_Radial_D6.3mm_P2.50mm"
FP_DECOUPLE = "Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm"
FP_HOLE = "MountingHole:MountingHole_3.2mm_M3"

U1, U2, J1, J2, J3, C1, C2 = "U1", "U2", "J1", "J2", "J3", "C1", "C2"
HOLES = ["H1", "H2", "H3", "H4"]

# 74AHCT125 (74LS125 pinout). Gate 1 carries the pixel data; gates 2-4 are
# disabled (OE high) with their inputs held low so nothing floats.
SHIFTER = {
    "1OE": 1, "1A": 2, "1Y": 3, "2OE": 4, "2A": 5, "2Y": 6, "GND": 7,
    "3Y": 8, "3A": 9, "3OE": 10, "4Y": 11, "4A": 12, "4OE": 13, "VCC": 14,
}  # fmt: skip
SHIFTER_OPEN = ["2Y", "3Y", "4Y"]

# The serial header, pin for pin as the stripboard's: ground, then the
# Teensy's RX, then its TX. The cable crosses them over to the Portal.
SERIAL_PINS = {1: "GND", 2: "SERIAL_RX", 3: "SERIAL_TX"}


def harness_teensy_pin(pos):
    """What a harness position carries at this end: a Teensy pin, or a net."""
    pin = BB.RIBBON_TEENSY[pos - 1]
    if pin == 10:
        return "GND"  # audio-reserved pin 10's position, reused for ground
    if pin == "3V3":
        return "PIXEL_5V"  # 3.3 V's position, reused for the shifted data
    return pin


def switch_names():
    """Teensy pin -> switch net name, named as the button board names them."""
    p1, p2 = BB.config_pins()
    names = {}
    for player, pins in (("P1", p1), ("P2", p2)):
        for colour, pin in zip(BB.CAP_COLOURS + ["START"], pins):
            names[pin] = f"SW_{player}_{colour}"
    return names


def build():
    """Return (components, nets): components as (ref, value, footprint, note)."""
    comps = [
        (U1, "Teensy 4.1", FP_TEENSY, "socketed; cut the VIN-VUSB pad"),
        (U2, "74AHCT125", FP_SHIFTER, "pixel data 3.3 V -> 5 V"),
        (J1, "1x14", FP_HARNESS, "harness to button board J13"),
        (J2, "B3B-XH-A", FP_SERIAL, "Serial1 to Matrix Portal"),
        (J3, "MX126-5.0-02P", FP_PWR, "+5V in, from the star"),
        (C1, "100uF/16V", FP_BULK, "bulk at the power entry"),
        (C2, "100nF", FP_DECOUPLE, "74AHCT125 decoupling"),
    ]
    comps += [(ref, "M3", FP_HOLE, "mounting hole, unplated") for ref in HOLES]

    nets = defaultdict(list)
    nets["+5V"] += [(J3, 1), (U1, teensy_pad("VIN")), (C1, 1), (C2, 2)]
    nets["+5V"] += [(U2, SHIFTER[p]) for p in ("VCC", "2OE", "3OE", "4OE")]
    nets["GND"] += [(J3, 2), (C1, 2), (C2, 1), (J2, 1)]
    nets["GND"] += [(U1, teensy_pad("GND", n)) for n in range(3)]
    nets["GND"] += [(U2, SHIFTER[p]) for p in ("GND", "1OE", "2A", "3A", "4A")]

    nets["PIXEL_3V3"] = [(U1, teensy_pad(PIXEL_PIN)), (U2, SHIFTER["1A"])]
    nets["PIXEL_5V"] = [(U2, SHIFTER["1Y"])]
    nets["SERIAL_RX"] = [(J2, 2), (U1, teensy_pad(SERIAL_RX))]
    nets["SERIAL_TX"] = [(J2, 3), (U1, teensy_pad(SERIAL_TX))]

    names = switch_names()
    for pos in range(1, 15):
        carries = harness_teensy_pin(pos)
        if isinstance(carries, str):
            nets[carries].append((J1, pos))
        elif carries in names:
            nets[names[carries]] = [(J1, pos), (U1, teensy_pad(carries))]
        else:
            sys.exit(f"harness position {pos} lands on Teensy pin {carries}, no button")
    return comps, dict(nets)


def validate(comps, nets):
    """Every connector pin on exactly one net; every net with two ends."""
    expect = {J1: set(range(1, 15)), J2: {1, 2, 3}, J3: {1, 2}, C1: {1, 2}, C2: {1, 2}}
    expect[U2] = {n for p, n in SHIFTER.items() if p not in SHIFTER_OPEN}
    seen = defaultdict(list)
    for nodes in nets.values():
        for ref, pin in nodes:
            seen[ref].append(pin)
    problems = []
    for ref, pins in expect.items():
        got = seen[ref]
        dupes = sorted({p for p in got if got.count(p) > 1})
        if dupes:
            problems.append(f"{ref}: pin(s) {dupes} on more than one net")
        if pins - set(got):
            problems.append(f"{ref}: pin(s) {sorted(pins - set(got))} on no net")
        if set(got) - pins:
            problems.append(f"{ref}: pin(s) {sorted(set(got) - pins)} should be open")
    teensy = seen[U1]
    if len(teensy) != len(set(teensy)):
        problems.append("U1: a Teensy pad is on more than one net")
    for name, nodes in nets.items():
        if len(nodes) < 2:
            problems.append(f"net {name} has only {len(nodes)} node")
    return problems


def table(comps, nets):
    out = ["COMPONENTS", "-" * 72]
    for ref, val, fp, note in comps:
        out.append(f"{ref:<4} {val:<14} {note}")
        out.append(f"     {fp}")
    out += ["", f"NETS ({len(nets)})", "-" * 72]
    for name in sorted(nets, key=lambda n: (n not in ("+5V", "GND"), n)):
        nodes = []
        for ref, pin in nets[name]:
            label = f"[{TEENSY_PINS[pin - 1]}]" if ref == U1 else ""
            nodes.append(f"{ref}.{pin}{label}")
        out.append(f"{name:<16} {', '.join(nodes)}")
    return "\n".join(out)


def main():
    comps, nets = build()
    problems = validate(comps, nets)
    if problems:
        print("netlist is inconsistent:", file=sys.stderr)
        for p in problems:
            print("  " + p, file=sys.stderr)
        return 1
    print(table(comps, nets))
    return 0


if __name__ == "__main__":
    sys.exit(main())
