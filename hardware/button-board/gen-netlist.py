#!/usr/bin/env python3
"""Generate the button board netlist for KiCad, and a readable net table.

The board is twelve connectors, three power nets and one daisy chain -- all of
it derivable, none of it worth drawing by hand twice. Everything below comes
from one description, so the KiCad netlist and the human-readable table cannot
disagree with each other.

The cap order IS the pixel index order: J1..J10 are P1 blue through P2 yellow,
which is the order WS2812 data flows and the order Config.h addresses. Ribbon
positions follow kP1ButtonPins / kP2ButtonPins.

    python3 hardware/button-board/gen-netlist.py            # net table
    python3 hardware/button-board/gen-netlist.py --kicad    # KiCad netlist

Import with pcbnew: File > Import > Netlist. Footprint names are checked
against KiCad 10's libraries; verify them if you are on a different release.
"""

import argparse
import pathlib
import sys
from collections import defaultdict

FP_CAP = "Connector_JST:JST_XH_B6B-XH-A_1x06_P2.50mm_Vertical"
FP_START = "Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical"
FP_RIBBON = "Connector_JST:JST_XH_B14B-XH-A_1x14_P2.50mm_Vertical"
# Deliberately NOT a JST XH. J11, J12 and J14 are all 2-pin, and a power lead
# in a start-button socket puts +5 V onto a Teensy input through the switch
# line. A screw terminal cannot accept an XH plug at all, so the mistake stops
# being possible rather than merely unlikely. 5 mm pitch, 1.3 mm drill: the
# common KF301/DG126/MX126 part, and it takes 18-22 AWG directly.
FP_PWR = "TerminalBlock:TerminalBlock_MaiXu_MX126-5.0-02P_1x02_P5.00mm"
FP_CAP1000 = "Capacitor_THT:CP_Radial_D10.0mm_P5.00mm"
FP_NETTIE = "NetTie:NetTie-2_THT_Pad1.0mm"
# Unplated. A plated hole would tie GND_LED to whatever the board bolts to at
# four points, which is exactly the many-paths-to-ground the net tie exists to
# prevent. The screws are structure, not a conductor.
FP_HOLE = "MountingHole:MountingHole_3.2mm_M3"

# The ribbon's fourteen positions in order, as the Teensy pin each one lands on.
# Positions 2 and 5 reach pin 10 (reserved for audio) and 3.3 V, so their strips
# are cut on the controller board and reused for ground and pixel data.
RIBBON_TEENSY = [9, 10, 11, 12, "3V3", 24, 25, 26, 27, 28, 29, 30, 31, 32]
# Resolved against the repo, not the working directory: these scripts are run
# from wherever is convenient, and a CWD-relative path here fails after the
# shell has already truncated the redirect target.
CFG = pathlib.Path(__file__).resolve().parents[2] / "firmware/WhackAMole/Config.h"
CAP_COLOURS = ["BLUE", "RED", "WHITE", "GREEN", "YELLOW"]


def config_pins(path=CFG):
    """Read kP1ButtonPins / kP2ButtonPins so this cannot drift from the firmware."""
    import re

    with open(path) as handle:
        src = handle.read()

    def arr(name):
        m = re.search(name + r"\[\w+\]\s*=\s*\{([^}]*)\}", src)
        if not m:
            sys.exit(f"could not find {name} in {path}")
        return [int(v) for v in m.group(1).split(",")]

    return arr("kP1ButtonPins"), arr("kP2ButtonPins")


def ribbon_pos(teensy_pin):
    """Which ribbon position carries a given Teensy pin."""
    try:
        return RIBBON_TEENSY.index(teensy_pin) + 1
    except ValueError:
        sys.exit(f"Teensy pin {teensy_pin} is not on the ribbon")


def connectors():
    """Cap connectors in pixel-chain order, then the two start buttons.

    J1..J10 ARE the chain: P1 blue through P2 yellow, which is both the order
    data flows and the order Config.h addresses the pixels.
    """
    p1, p2 = config_pins()
    caps, starts = [], []
    for i, colour in enumerate(CAP_COLOURS):
        caps.append((f"J{i + 1}", f"P1 {colour}", ribbon_pos(p1[i])))
    for i, colour in enumerate(CAP_COLOURS):
        caps.append((f"J{i + 6}", f"P2 {colour}", ribbon_pos(p2[i])))
    starts.append(("J11", "P1 START", ribbon_pos(p1[5])))
    starts.append(("J12", "P2 START", ribbon_pos(p2[5])))
    return caps, starts


CAPS, STARTS = connectors()

RIBBON, POWER, C1, NT1 = "J13", "J14", "C1", "NT1"

# M3 mounting holes. They carry no net, so they exist here only so that
# "Update PCB from Schematic" sees a symbol behind each one -- a footprint with
# no symbol is the kind KiCad offers to delete for you.
HOLES = ["H1", "H2", "H3", "H4"]

# Cap connector pinout, as wired in the caps already built.
CAP_PINS = {1: "+5V", 2: "DIN", 3: "GND", 4: "DOUT", 5: "SW", 6: "SWGND"}


def build():
    """Return (components, nets) where nets maps name -> [(ref, pin), ...]."""
    comps = []
    for ref, label, _ in CAPS:
        comps.append((ref, "B6B-XH-A", FP_CAP, label))
    for ref, label, _ in STARTS:
        comps.append((ref, "B2B-XH-A", FP_START, label))
    comps.append((RIBBON, "1x14", FP_RIBBON, "to controller"))
    comps.append((POWER, "MX126-5.0-02P", FP_PWR, "+5V in, from HUSB238"))
    comps.append((C1, "1000uF/16V", FP_CAP1000, "bulk at the star"))
    comps.append((NT1, "NetTie", FP_NETTIE, "LED GND to SW GND, single point"))
    for ref in HOLES:
        comps.append((ref, "M3", FP_HOLE, "mounting hole, unplated"))

    nets = defaultdict(list)

    # Power. The two returns are separate nets joined only at the net tie --
    # that single point is what makes this a star, and what keeps ring current
    # out of the switch reference.
    for ref, _, _ in CAPS:
        nets["+5V"].append((ref, 1))
        nets["GND_LED"].append((ref, 3))
        nets["GND_SW"].append((ref, 6))
    for ref, _, _ in STARTS:
        nets["GND_SW"].append((ref, 2))
    nets["+5V"] += [(POWER, 1), (C1, 1)]
    nets["GND_LED"] += [(POWER, 2), (C1, 2), (NT1, 1)]
    nets["GND_SW"] += [(RIBBON, 2), (NT1, 2)]

    # Pixel chain: ribbon position 5 into the first cap, then DOUT to DIN down
    # the line. The last cap's DOUT is deliberately unterminated.
    nets["DATA_IN"] = [(RIBBON, 5), (CAPS[0][0], 2)]
    for i in range(len(CAPS) - 1):
        nets[f"DATA_{CAPS[i][0]}_{CAPS[i + 1][0]}"] = [
            (CAPS[i][0], 4),
            (CAPS[i + 1][0], 2),
        ]

    # Switch signals, one net per button.
    for ref, label, pos in CAPS:
        nets["SW_" + label.replace(" ", "_")] = [(ref, 5), (RIBBON, pos)]
    for ref, label, pos in STARTS:
        nets["SW_" + label.replace(" ", "_")] = [(ref, 1), (RIBBON, pos)]

    return comps, dict(nets)


def validate(comps, nets):
    """Every connector pin must appear exactly once, except the open DOUT."""
    expect = {}
    for ref, _, _ in CAPS:
        expect[ref] = set(CAP_PINS)
    for ref, _, _ in STARTS:
        expect[ref] = {1, 2}
    expect[RIBBON] = set(range(1, 15))
    expect[POWER] = {1, 2}
    expect[C1] = {1, 2}
    expect[NT1] = {1, 2}

    seen = defaultdict(list)
    for name, nodes in nets.items():
        for ref, pin in nodes:
            seen[ref].append((pin, name))

    problems = []
    for ref, pins in expect.items():
        got = [p for p, _ in seen[ref]]
        dupes = {p for p in got if got.count(p) > 1}
        if dupes:
            problems.append(f"{ref}: pin(s) {sorted(dupes)} on more than one net")
        missing = pins - set(got)
        # The last cap's DOUT is the end of the chain and connects to nothing.
        if ref == CAPS[-1][0]:
            missing -= {4}
        if missing:
            problems.append(f"{ref}: pin(s) {sorted(missing)} on no net")
        extra = set(got) - pins
        if extra:
            problems.append(f"{ref}: pin(s) {sorted(extra)} do not exist")

    for name, nodes in nets.items():
        if len(nodes) < 2:
            problems.append(f"net {name} has only {len(nodes)} node")
    return problems


def table(comps, nets):
    out = ["COMPONENTS", "-" * 72]
    for ref, val, fp, note in comps:
        out.append(f"{ref:<5} {val:<14} {note}")
        out.append(f"      {fp}")
    out += ["", f"NETS ({len(nets)})", "-" * 72]
    for name in sorted(nets, key=lambda n: (not n.startswith(("+5V", "GND")), n)):
        nodes = ", ".join(f"{r}.{p}" for r, p in nets[name])
        out.append(f"{name:<22} {nodes}")
    out += [
        "",
        "NOT CONNECTED",
        "-" * 72,
        f"{CAPS[-1][0]}.4   DOUT of {CAPS[-1][1]} -- end of the pixel chain",
    ]
    return "\n".join(out)


def kicad(comps, nets):
    o = ['(export (version "E")', "  (design)", "  (components"]
    for ref, val, fp, note in comps:
        o.append(f'    (comp (ref "{ref}") (value "{val}") (footprint "{fp}")')
        o.append(f'      (fields (field (name "Note") "{note}")))')
    o.append("  )")
    o.append("  (nets")
    for i, name in enumerate(sorted(nets), start=1):
        o.append(f'    (net (code "{i}") (name "{name}")')
        for ref, pin in nets[name]:
            o.append(f'      (node (ref "{ref}") (pin "{pin}") (pintype "passive"))')
        o.append("    )")
    o.append("  )")
    o.append(")")
    return "\n".join(o)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kicad", action="store_true", help="emit a KiCad netlist")
    args = ap.parse_args()

    comps, nets = build()
    problems = validate(comps, nets)
    if problems:
        print("netlist is inconsistent:", file=sys.stderr)
        for p in problems:
            print("  " + p, file=sys.stderr)
        return 1

    print(kicad(comps, nets) if args.kicad else table(comps, nets))
    return 0


if __name__ == "__main__":
    sys.exit(main())
