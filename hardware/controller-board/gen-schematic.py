#!/usr/bin/env python3
"""Generate the controller board's schematic from gen-netlist.py.

Drawn the way the button board's is: every connected pin gets a short stub and
a net label, so a connection is made by name and cannot be a wire that lands a
hair off a pin and silently connects nothing. Stock symbols are lifted from
the installed KiCad libraries; the Teensy 4.1, which KiCad does not ship, is
written into this project's own library first.

UUIDs are derived from reference designators, not random, so gen-pcb.py can
link each footprint to its symbol without the two scripts sharing any state --
and so regenerating either one does not orphan the other.

    python3 hardware/controller-board/gen-schematic.py

Writes controller-board/controller-board.kicad_sch and controller-board.kicad_sym.
Verify with:
    kicad-cli sch erc controller-board/controller-board.kicad_sch
"""

import importlib.util
import pathlib
import re
import sys
import uuid

HERE = pathlib.Path(__file__).resolve().parent
PROJECT = HERE / "controller-board"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


NL = _load("controller_netlist", HERE / "gen-netlist.py")
BBS = _load("button_schematic", HERE.parent / "button-board" / "gen-schematic.py")

NS = uuid.UUID("6f1d3b2e-6c51-4c2a-9a55-0c7e1b2a9d10")
ROOT_UUID = str(uuid.uuid5(NS, "controller-board:root"))


def sym_uuid(ref, unit=1):
    """The symbol's UUID, which gen-pcb.py also derives as the footprint link."""
    return str(uuid.uuid5(NS, f"symbol:{ref}" if unit == 1 else f"symbol:{ref}:{unit}"))


def uid():
    return BBS.uid()


G = 1.27  # KiCad's connection grid; every coordinate is a multiple of it
STUB = 5.08

# --- The Teensy 4.1 symbol -------------------------------------------------

TEENSY_LIB = "controller-board"
TEENSY_NAME = "Teensy4.1"
TEENSY_HALF = 12  # body half-width, in grid units


def teensy_symbol(keyed=False):
    """The Teensy as a symbol: left row down the left, right row down the right.

    Pins are passive. The board feeds it 5 V on VIN and takes nothing from its
    3.3 V pins, so there is no supply relationship for ERC to reason about.
    """
    name = f"{TEENSY_LIB}:{TEENSY_NAME}" if keyed else TEENSY_NAME
    top = 24 * 2 - 1  # first pin row, grid units above centre
    o = [
        f'(symbol "{name}" (pin_names (offset 1.016)) (exclude_from_sim no)'
        " (in_bom yes) (on_board yes)",
        f'  (property "Reference" "U" (at 0 {(top + 3) * G:.2f} 0)'
        " (effects (font (size 1.27 1.27))))",
        f'  (property "Value" "Teensy 4.1" (at 0 {-(top + 3) * G:.2f} 0)'
        " (effects (font (size 1.27 1.27))))",
        f'  (property "Footprint" "{NL.FP_TEENSY}" (at 0 0 0)'
        " (effects (font (size 1.27 1.27)) hide))",
        '  (property "Datasheet" "https://www.pjrc.com/store/teensy41.html" (at 0 0 0)'
        " (effects (font (size 1.27 1.27)) hide))",
        '  (property "Description" "Teensy 4.1, outer pin rows only, socketed"'
        " (at 0 0 0) (effects (font (size 1.27 1.27)) hide))",
        f'  (symbol "{TEENSY_NAME}_0_1"',
        f"    (rectangle (start {-TEENSY_HALF * G:.2f} {(top + 1) * G:.2f})"
        f" (end {TEENSY_HALF * G:.2f} {-(top + 1) * G:.2f})"
        " (stroke (width 0.254) (type default)) (fill (type background)))",
        "  )",
        f'  (symbol "{TEENSY_NAME}_1_1"',
    ]
    for i, label in enumerate(NL.TEENSY_LEFT):
        y = (top - 2 * i) * G
        o.append(
            f"    (pin passive line (at {-(TEENSY_HALF + 2) * G:.2f} {y:.2f} 0)"
            f' (length 2.54) (name "{label}" (effects (font (size 1.27 1.27))))'
            f' (number "{i + 1}" (effects (font (size 1.27 1.27)))))'
        )
    for i, label in enumerate(NL.TEENSY_RIGHT):
        y = (top - 2 * i) * G
        o.append(
            f"    (pin passive line (at {(TEENSY_HALF + 2) * G:.2f} {y:.2f} 180)"
            f' (length 2.54) (name "{label}" (effects (font (size 1.27 1.27))))'
            f' (number "{i + 25}" (effects (font (size 1.27 1.27)))))'
        )
    o += ["  )", ")"]
    return "\n".join(o)


def teensy_pins():
    """Pin number -> (x, y, angle) in symbol space, as for lifted symbols."""
    pins = {}
    for m in re.finditer(
        r"\(pin passive line \(at ([-\d.]+) ([-\d.]+) (\d+)\).*?\(number \"(\d+)\"",
        teensy_symbol(),
    ):
        pins[m.group(4)] = (float(m.group(1)), float(m.group(2)), int(m.group(3)))
    return pins


# --- Stock symbols ----------------------------------------------------------

# ref -> (library, symbol). The '125 is placed as its 74LS125 parent: KiCad's
# 74AHCT125 is a derived symbol, which cannot be embedded in a schematic as is,
# and the pinout is identical. The Value says what to buy.
STOCK = {
    NL.U2: ("74xx", "74LS125"),
    NL.J1: ("Connector_Generic", "Conn_01x14"),
    NL.J2: ("Connector_Generic", "Conn_01x03"),
    NL.J3: ("Connector_Generic", "Conn_01x02"),
    NL.C1: ("Device", "C_Polarized"),
    NL.C2: ("Device", "C"),
}
for _ref in NL.HOLES:
    STOCK[_ref] = ("Mechanical", "MountingHole")
PWR_FLAG = ("power", "PWR_FLAG")


def unit_pins(lib, name):
    """Pin number -> (unit, x, y, angle). Unit 0 means common to all units."""
    body = BBS.lift_symbol(lib, name)
    starts = [
        (m.start(), int(m.group(1)))
        for m in re.finditer(rf'\(symbol "{re.escape(name)}_(\d+)_\d+"', body)
    ]
    pins = {}
    for m in re.finditer(
        r"\(pin \w+ \w+\s*\(at ([-\d.]+) ([-\d.]+) (\d+)\).*?\(number \"([^\"]+)\"",
        body,
        re.S,
    ):
        unit = max((u for pos, u in starts if pos < m.start()), default=0)
        pins[m.group(4)] = (unit, float(m.group(1)), float(m.group(2)), int(m.group(3)))
    return pins


def stub(place, pin_xy_angle):
    """Pin end and label end in schematic space. Symbol Y is inverted."""
    (x, y), (sx, sy, angle) = place, pin_xy_angle
    dx, dy = {0: (-1, 0), 90: (0, -1), 180: (1, 0), 270: (0, 1)}[angle]
    pin = (round(x + sx, 4), round(y - sy, 4))
    end = (round(x + sx + dx * STUB, 4), round(y - (sy + dy * STUB), 4))
    return pin, end, angle


def grid(gx, gy):
    return (round(gx * G, 4), round(gy * G, 4))


# Placement in grid units: the Teensy in the middle, what it talks to around it.
PLACE = {
    (NL.U1, 1): grid(140, 90),
    (NL.J1, 1): grid(60, 110),
    (NL.J2, 1): grid(60, 50),
    (NL.J3, 1): grid(220, 40),
    (NL.C1, 1): grid(250, 40),
    (NL.C2, 1): grid(270, 40),
    (NL.U2, 1): grid(220, 90),
    (NL.U2, 2): grid(220, 110),
    (NL.U2, 3): grid(220, 130),
    (NL.U2, 4): grid(220, 150),
    (NL.U2, 5): grid(260, 110),
}
for _i, _ref in enumerate(NL.HOLES):
    PLACE[(_ref, 1)] = grid(60 + 16 * _i, 170)
FLAGS = {"+5V": grid(300, 40), "GND": grid(320, 40)}


# Where a symbol's text sits, relative to its origin, when the default (just
# right of and above a small symbol) would land on the body or its labels.
FIELDS_AT = {
    NL.U1: (-15.24, -71.12),
    NL.U2: (-3.81, -12.7),
}


def instance(o, ref, lib_id, unit, at, value, footprint, note, pin_numbers):
    x, y = at
    fx, fy = FIELDS_AT.get(ref, (3.81, -6.35))
    if ref in NL.HOLES:
        note = ""  # four identical notes in a row only collide
    # Mounting holes are not parts to order, and their footprints say so.
    in_bom = "no" if ref in NL.HOLES else "yes"
    o.append("  (symbol")
    o.append(f'    (lib_id "{lib_id}") (at {x} {y} 0) (unit {unit})')
    o.append(f"    (exclude_from_sim no) (in_bom {in_bom}) (on_board yes)")
    o.append(f'    (uuid "{sym_uuid(ref, unit)}")')
    hide = "" if unit == 1 else " hide"
    o.append(
        f'    (property "Reference" "{ref}" (at {x + fx} {y + fy} 0)'
        f" (effects (font (size 1.27 1.27)) (justify left){hide}))"
    )
    o.append(
        f'    (property "Value" "{value}" (at {x + fx} {y + fy + 2.54} 0)'
        f" (effects (font (size 1.27 1.27)) (justify left){hide}))"
    )
    o.append(
        f'    (property "Footprint" "{footprint}" (at {x} {y} 0)'
        " (effects (font (size 1.27 1.27)) hide))"
    )
    if note:
        o.append(
            f'    (property "Note" "{note}" (at {x + fx} {y + fy + 5.08} 0)'
            f" (effects (font (size 1.0 1.0)) (justify left){hide}))"
        )
    for p in pin_numbers:
        o.append(f'    (pin "{p}" (uuid "{uid()}"))')
    o.append(
        f'    (instances (project "controller-board"'
        f' (path "/{ROOT_UUID}" (reference "{ref}") (unit {unit}))))'
    )
    o.append("  )")


def label(o, pin, end, angle, net):
    o.append(
        f"  (wire (pts (xy {pin[0]} {pin[1]}) (xy {end[0]} {end[1]}))"
        f' (stroke (width 0) (type default)) (uuid "{uid()}"))'
    )
    # Text runs away from the symbol: leftward off a left-hand pin, rightward
    # off a right-hand one, down off a bottom pin and up off a top one. KiCad
    # draws 180-degree text upright, so "away to the left" is angle 0 anchored
    # at its right end, not angle 180.
    rot, justify = {0: (0, "right"), 180: (0, "left"), 90: (270, "left"), 270: (90, "left")}[angle]
    o.append(
        f'  (label "{net}" (at {end[0]} {end[1]} {rot})'
        f' (effects (font (size 1.27 1.27)) (justify {justify})) (uuid "{uid()}"))'
    )


def write_library():
    lib = PROJECT / "controller-board.kicad_sym"
    lib.write_text(
        '(kicad_symbol_lib (version 20231120) (generator "gen-schematic.py")\n'
        + teensy_symbol()
        + "\n)\n"
    )


def main():
    comps, nets = NL.build()
    problems = NL.validate(comps, nets)
    if problems:
        print("refusing to draw an inconsistent netlist:", file=sys.stderr)
        for p in problems:
            print("  " + p, file=sys.stderr)
        return 1
    PROJECT.mkdir(exist_ok=True)
    write_library()

    pin_net = {(ref, pin): name for name, nodes in nets.items() for ref, pin in nodes}
    info = {ref: (val, fp, note) for ref, val, fp, note in comps}

    o = [
        "(kicad_sch",
        "  (version 20231120)",
        '  (generator "gen-schematic.py")',
        '  (generator_version "8.0")',
        f'  (uuid "{ROOT_UUID}")',
        '  (paper "A3")',
        '  (title_block (title "Whack-A-Mole Attack - controller board")'
        ' (comment 1 "Generated by hardware/controller-board/gen-schematic.py"))',
        "  (lib_symbols",
    ]
    o += ["    " + line for line in teensy_symbol(keyed=True).splitlines()]
    for lib, name in sorted(set(STOCK.values()) | {PWR_FLAG}):
        o += ["    " + line for line in BBS.lift_symbol(lib, name).splitlines()]
    o.append("  )")

    open_pins = []

    # Teensy: one unit, its own library.
    tpins = teensy_pins()
    val, fp, note = info[NL.U1]
    at = PLACE[(NL.U1, 1)]
    instance(o, NL.U1, f"{TEENSY_LIB}:{TEENSY_NAME}", 1, at, val, fp, note, sorted(tpins, key=int))
    for num, geom in tpins.items():
        pin, end, angle = stub(at, geom)
        net = pin_net.get((NL.U1, int(num)))
        if net:
            label(o, pin, end, angle, net)
        else:
            open_pins.append(pin)

    # Stock parts, unit by unit.
    for ref, (lib, name) in STOCK.items():
        pins = unit_pins(lib, name)
        units = sorted({u for u, *_ in pins.values()} - {0}) or [1]
        val, fp, note = info[ref]
        for unit in units:
            at = PLACE[(ref, unit)]
            mine = [n for n, (u, *_) in pins.items() if u in (0, unit)]
            instance(o, ref, f"{lib}:{name}", unit, at, val, fp, note, sorted(mine, key=int))
            for num in mine:
                _, sx, sy, angle = pins[num]
                pin, end, angle = stub(at, (sx, sy, angle))
                net = pin_net.get((ref, int(num)))
                if net:
                    label(o, pin, end, angle, net)
                else:
                    open_pins.append(pin)

    # One PWR_FLAG per supply net: the '125's VCC and GND are power inputs, and
    # ERC wants to see something declared as driving them. The terminal block
    # does, but a connector pin cannot say so.
    flag_pin = unit_pins(*PWR_FLAG)["1"]
    for i, (net, at) in enumerate(FLAGS.items()):
        ref = f"#FLG0{i + 1}"
        o.append("  (symbol")
        o.append(f'    (lib_id "power:PWR_FLAG") (at {at[0]} {at[1]} 0) (unit 1)')
        o.append("    (exclude_from_sim no) (in_bom yes) (on_board yes)")
        o.append(f'    (uuid "{sym_uuid(ref)}")')
        o.append(
            f'    (property "Reference" "{ref}" (at {at[0]} {at[1] - 3} 0)'
            " (effects (font (size 1.27 1.27)) hide))"
        )
        o.append(
            f'    (property "Value" "PWR_FLAG" (at {at[0]} {at[1] - 5} 0)'
            " (effects (font (size 1.27 1.27))))"
        )
        o.append(f'    (pin "1" (uuid "{uid()}"))')
        o.append(
            f'    (instances (project "controller-board"'
            f' (path "/{ROOT_UUID}" (reference "{ref}") (unit 1))))'
        )
        o.append("  )")
        _, sx, sy, angle = flag_pin
        pin, end, angle = stub(at, (sx, sy, angle))
        label(o, pin, end, angle, net)

    # Every pin left open is open on purpose: the Teensy's unused pins and the
    # three disabled '125 outputs. Saying so turns ERC's "unconnected" into a
    # statement rather than a question.
    for x, y in open_pins:
        o.append(f'  (no_connect (at {x} {y}) (uuid "{uid()}"))')

    o.append('  (sheet_instances (path "/" (page "1")))')
    o.append(")")
    (PROJECT / "controller-board.kicad_sch").write_text("\n".join(o) + "\n")
    print(f"wrote {PROJECT.name}/controller-board.kicad_sch and controller-board.kicad_sym")
    return 0


if __name__ == "__main__":
    sys.exit(main())
