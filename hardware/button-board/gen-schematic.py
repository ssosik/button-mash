#!/usr/bin/env python3
"""Generate button-board.kicad_sch from the netlist in gen-netlist.py.

Connections are made with net labels on short pin stubs rather than drawn
wires. For a board that is twelve connectors and three buses that is the
clearer drawing anyway, and it removes the whole class of bugs where a
generated wire lands a hair off a pin and silently connects nothing.

Symbol definitions are lifted from the installed KiCad libraries rather than
written out here, so they match whatever version is on this machine.

    python3 hardware/button-board/gen-schematic.py > button-board.kicad_sch

Verify with:
    kicad-cli sch erc button-board.kicad_sch
    kicad-cli sch export netlist button-board.kicad_sch
"""

import importlib.util
import pathlib
import re
import sys
import uuid

HERE = pathlib.Path(__file__).parent
SYMDIR = pathlib.Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols")

spec = importlib.util.spec_from_file_location("netlist", HERE / "gen-netlist.py")
NL = importlib.util.module_from_spec(spec)
spec.loader.exec_module(NL)

# component ref -> (library, symbol, pin count)
SYMBOL = {}
for ref, _, _ in NL.CAPS:
    SYMBOL[ref] = ("Connector_Generic", "Conn_01x06", 6)
for ref, _, _ in NL.STARTS:
    SYMBOL[ref] = ("Connector_Generic", "Conn_01x02", 2)
SYMBOL[NL.RIBBON] = ("Connector_Generic", "Conn_01x14", 14)
SYMBOL[NL.POWER] = ("Connector_Generic", "Conn_01x02", 2)
SYMBOL[NL.C1] = ("Device", "C_Polarized", 2)
SYMBOL[NL.NT1] = ("Device", "NetTie_2", 2)
for ref in NL.HOLES:
    SYMBOL[ref] = ("Mechanical", "MountingHole", 0)

STUB = 5.08  # how far the label sits off the pin

# Pin geometry is read out of the symbol rather than modelled. Guessing it is
# how the first attempt put every stub 2.54 mm off its pin and produced 349
# dangling-label errors: a wire that misses a pin connects nothing, silently.
_PIN_CACHE = {}


def uid():
    return str(uuid.uuid4())


def lift_symbol(lib, name):
    """Pull one symbol's full definition out of an installed .kicad_sym."""
    src = (SYMDIR / f"{lib}.kicad_sym").read_text()
    start = src.index(f'(symbol "{name}"')
    depth, i = 0, start
    while True:  # walk to the matching close paren
        if src[i] == "(":
            depth += 1
        elif src[i] == ")":
            depth -= 1
            if depth == 0:
                break
        i += 1
    body = src[start : i + 1]
    # inside a schematic the symbol is keyed "Lib:Name"
    return body.replace(f'(symbol "{name}"', f'(symbol "{lib}:{name}"', 1)


def symbol_pins(lib, name):
    """Pin number -> (x, y, angle) in symbol space, straight from the library."""
    key = (lib, name)
    if key in _PIN_CACHE:
        return _PIN_CACHE[key]
    body = lift_symbol(lib, name)
    pins = {}
    for m in re.finditer(
        r"\(pin \w+ \w+\s*\(at ([-\d.]+) ([-\d.]+) (\d+)\)"
        r'\s*\(length [\d.]+\).*?\(number "([^"]+)"',
        body,
        re.S,
    ):
        pins[m.group(4)] = (float(m.group(1)), float(m.group(2)), int(m.group(3)))
    _PIN_CACHE[key] = pins
    return pins


def stub_for(place_x, place_y, lib, name, pin):
    """Schematic coords of a pin and of its label stub end.

    A pin's angle points from its connection end toward the body, so the stub
    runs the other way. Symbol Y is inverted going into the schematic.
    """
    sx, sy, angle = symbol_pins(lib, name)[str(pin)]
    dx, dy = {0: (-1, 0), 90: (0, -1), 180: (1, 0), 270: (0, 1)}[angle]
    px, py = place_x + sx, place_y - sy
    ex, ey = place_x + sx + dx * STUB, place_y - (sy + dy * STUB)
    return (px, py), (ex, ey), angle


def main():
    comps, nets = NL.build()
    problems = NL.validate(comps, nets)
    if problems:
        print("refusing to draw an inconsistent netlist:", file=sys.stderr)
        for p in problems:
            print("  " + p, file=sys.stderr)
        return 1

    pin_net = {}
    for name, nodes in nets.items():
        for ref, pin in nodes:
            pin_net[(ref, pin)] = name

    o = [
        "(kicad_sch",
        "  (version 20231120)",
        '  (generator "gen-schematic.py")',
        '  (generator_version "8.0")',
        f'  (uuid "{uid()}")',
        '  (paper "A2")',
    ]

    o.append("  (lib_symbols")
    for lib, name in sorted({(lib, n) for lib, n, _ in SYMBOL.values()}):
        for line in lift_symbol(lib, name).splitlines():
            o.append("    " + line)
    o.append("  )")

    # Lay the connectors out in two columns, caps left and right as on the board.
    order = (
        [r for r, _, _ in NL.CAPS]
        + [r for r, _, _ in NL.STARTS]
        + [NL.RIBBON, NL.POWER, NL.C1, NL.NT1]
        + NL.HOLES
    )
    # Everything must land on KiCad's 1.27 mm connection grid. An origin that
    # is off-grid drags every pin with it and ERC fills with endpoint_off_grid,
    # so positions are expressed in grid units and multiplied, never rounded.
    G = 1.27
    place = {}
    for i, ref in enumerate(order):
        col, row = divmod(i, 8)
        place[ref] = (round(G * (48 + col * 72), 4), round(G * (32 + row * 34), 4))

    comp_note = {c[0]: c[3] for c in comps}
    comp_val = {c[0]: c[1] for c in comps}
    comp_fp = {c[0]: c[2] for c in comps}

    for ref in order:
        lib, name, count = SYMBOL[ref]
        x, y = place[ref]
        o.append("  (symbol")
        o.append(f'    (lib_id "{lib}:{name}") (at {x} {y} 0) (unit 1)')
        o.append("    (exclude_from_sim no) (in_bom yes) (on_board yes)")
        o.append(f'    (uuid "{uid()}")')
        o.append(
            f'    (property "Reference" "{ref}" (at {x + 5} {y - 6} 0)'
            " (effects (font (size 1.27 1.27)) (justify left)))"
        )
        o.append(
            f'    (property "Value" "{comp_val[ref]}" (at {x + 5} {y - 3.5} 0)'
            " (effects (font (size 1.27 1.27)) (justify left)))"
        )
        o.append(
            f'    (property "Footprint" "{comp_fp[ref]}" (at {x} {y} 0)'
            " (effects (font (size 1.27 1.27)) hide))"
        )
        o.append(
            f'    (property "Note" "{comp_note[ref]}" (at {x + 5} {y - 1} 0)'
            " (effects (font (size 1.0 1.0)) (justify left)))"
        )
        for p in range(1, count + 1):
            o.append(f'    (pin "{p}" (uuid "{uid()}"))')
        o.append(
            f'    (instances (project "button-board"'
            f' (path "/{uid()}" (reference "{ref}") (unit 1))))'
        )
        o.append("  )")

    # One stub plus one label per connected pin. Unconnected pins get neither,
    # which is what makes the open DOUT visible as an ERC warning rather than
    # silently fine.
    for ref in order:
        _, _, count = SYMBOL[ref]
        x, y = place[ref]
        for p in range(1, count + 1):
            net = pin_net.get((ref, p))
            if net is None:
                continue
            lib, name, _ = SYMBOL[ref]
            (px, py), (ex, ey), angle = stub_for(x, y, lib, name, p)
            o.append(
                f"  (wire (pts (xy {px} {py}) (xy {ex} {ey}))"
                f' (stroke (width 0) (type default)) (uuid "{uid()}"))'
            )
            lang = 0 if angle in (0, 180) else 90
            o.append(
                f'  (label "{net}" (at {ex} {ey} {lang})'
                " (effects (font (size 1.27 1.27)) (justify right))"
                f' (uuid "{uid()}"))'
            )

    # The last cap's DOUT ends the chain. Flagging it explicitly is the
    # difference between "deliberately open" and "someone forgot a wire".
    last = NL.CAPS[-1][0]
    lib, name, _ = SYMBOL[last]
    (px, py), _, _ = stub_for(*place[last], lib, name, 4)
    o.append(f'  (no_connect (at {px} {py}) (uuid "{uid()}"))')

    o.append(")")
    print("\n".join(o))
    return 0


if __name__ == "__main__":
    sys.exit(main())
