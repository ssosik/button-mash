# Controller board

The controller stripboard from [the wiring reference](../../docs/mole-table-wiring.pdf)
— 33 cuts and nine jumpers around a socketed Teensy 4.1 — as a two-layer PCB. Same
parts, same connectors, same pinout: the harness to the button board, the serial cable
to the Matrix Portal and the 5 V lead from the star all plug into it unchanged.

![3D render of the controller board](../../docs/controller-board-3d.jpg)

## Files

| File | What |
| --- | --- |
| `gen-netlist.py` | The single source of truth. Harness positions come from the button board's generator and switch pins from `Config.h`, so neither can drift from it. |
| `gen-schematic.py` | Draws the schematic from that netlist, and writes the Teensy 4.1 symbol KiCad does not ship. |
| `gen-pcb.py` | Places, routes and pours the board through KiCad's own `pcbnew` API, and writes the Teensy footprint. |
| `controller-board/` | The KiCad project. Everything in it is generated. |
| `controller-board.pdf` | The schematic as a drawing. |

```sh
make controller-board   # regenerate all of it, then ERC, DRC and schematic parity
make board-render       # the 3D view above
```

`gen-pcb.py` has to run under the Python inside KiCad, the only one that can import
`pcbnew`; the Makefile knows where it is. Unlike the button board, nothing here is
laid out by hand, so regenerating is always safe: edit the generator, never the board.

## What it checks

`make controller-board` fails on any of these, warnings included:

- **ERC** — 0 errors, 0 warnings. Every open pin carries an explicit no-connect.
- **DRC** — 0 violations, 0 unconnected items.
- **Schematic parity** — every footprint is linked to its symbol and every pad
  carries the net the schematic gives it. The links are UUIDs derived from
  reference designators, so the two generators agree without sharing state.

The schematic's exported netlist also diffs clean against `gen-netlist.py` — 18 nets,
53 nodes — and the netlist validator refuses a pin on two nets, a pin on none, a net
with one end, or a disabled '125 output wired to anything.

## Layout

It copies the stripboard on purpose. The harness header sits one column from the
Teensy's left row, so twelve of its fourteen positions are a straight trace to the
Teensy pin opposite — the PCB version of "the strip is the wire". The other two arrive
from elsewhere, exactly as on the stripboard: position 2 is ground, from the pour, and
position 5 is the level-shifted pixel data, run down the board's left edge on the
bottom layer.

| Ref | Part | Notes |
| --- | --- | --- |
| U1 | Teensy 4.1 on two 1×24 female headers | **Cut the VIN–VUSB pad** on the Teensy, or USB and the star will fight. |
| U2 | 74AHCT125 in a DIP-14 socket | Gate 1 lifts pin 8 to 5 V. Gates 2–4 are disabled (OE high), inputs grounded. |
| J1 | 1×14 2.54 mm pin header | Takes the harness's socket end; mates with button board J13. Pin 1 is P1 BLUE. |
| J2 | B3B-XH-A | Serial1 to the Portal: 1 GND, 2 Teensy RX, 3 Teensy TX. The cable crosses 2 and 3. |
| J3 | MX126 screw terminal | +5 V and GND from the star. A screw terminal, as on the button board. |
| C1 | 100 µF / 16 V | Bulk at the power entry. Stripe to GND. |
| C2 | 100 nF ceramic | Decoupling, straight onto the '125's VCC pin. |
| H1–H4 | M3, unplated | Mounting. |

Ground is a pour on both layers. +5 V reaches VIN and C1 on the top layer, and runs
along the top edge on the bottom layer to the '125.

## Before ordering

This has been through every check KiCad offers, but not through a fab or a first
article. Open it in KiCad and look it over before you send it anywhere, and check
the Teensy footprint against a real Teensy and its headers — it is drawn from the
published 0.6" row spacing, not measured from a part.
