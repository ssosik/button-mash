# Button board

Twelve connectors, three power nets, one daisy chain. The stripboard version is
documented in [the wiring reference](../../docs/mole-table-wiring.pdf) — 63 cuts
and 31 hand-soldered wires. This directory is the PCB alternative.

## Files

| File | What |
| --- | --- |
| `gen-netlist.py` | The single source of truth. Everything else derives from it. |
| `gen-schematic.py` | Draws the schematic from that netlist. |
| `button-board/` | The KiCad project. `button-board.net` and `button-board.kicad_sch` in it are generated; `button-board.kicad_pcb` is laid out by hand. |
| `button-board.pdf` | The schematic as a drawing, for reading away from KiCad. |

```sh
cd hardware/button-board
python3 gen-netlist.py                               # readable net table
python3 gen-netlist.py --kicad > button-board/button-board.net
python3 gen-schematic.py       > button-board/button-board.kicad_sch

# Regenerating the schematic assigns fresh symbol UUIDs, so the board's
# footprint links go stale. Re-import with "Update PCB from Schematic" and
# tick "Re-link footprints to schematic symbols based on their reference
# designators", or the 20 existing footprints come back as orphans.
```

Connections are made with net labels on pin stubs rather than drawn wires. For
twelve connectors and three buses that is the clearer drawing, and it removes
the class of bug where a generated wire lands a fraction off a pin and silently
connects nothing.

Both outputs are checked, not assumed. ERC reports **0 errors, 0 warnings**, and
the schematic is exported back to a netlist and diffed against the hand-built
one — 25 nets and 83 nodes, matching exactly. ERC alone is not sufficient: an
earlier draft passed ERC while connecting nothing at all.

Ribbon positions are read out of `firmware/WhackAMole/Config.h` rather than
written down here, so the netlist cannot drift from the firmware the way the
documentation did three times. The generator also refuses to emit anything if a
connector pin lands on two nets, on none, or does not exist — verified against
injected faults, not only on correct input.

## Designators

`J1`–`J10` are the lit caps **in pixel-chain order**: P1 blue, red, white,
green, yellow, then P2 in the same sequence. That is both the order data flows
and the order `Config.h` addresses them, so the reference designator is the
pixel index. `J11`/`J12` are the start buttons, `J13` the ribbon to the
controller, `J14` power in from the HUSB238.

## The one thing layout must get right

`GND_LED` and `GND_SW` are **separate nets joined only at `NT1`**. That single
point is the star. A ground pour that merges them anywhere else puts up to
1.81 A of ring current through the switch reference, and the symptom is inputs
that misread while the LEDs are busy — intermittent, load-dependent, and
unpleasant to chase. Keep the net tie, and check it survives the pour.

Beyond that: `+5V` and `GND_LED` want wide copper, since they carry the ring
current. Everything else is signal.

## Footprints

Checked against KiCad 10's libraries. Verify them if you are on another release
— JST and pin header library names have moved between versions.
