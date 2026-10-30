#!/usr/bin/env python3
"""Verify docs/wiring.html's pin table still matches Config.h.

The document states that its pin assignments are mirrored from Config.h. Across
three pin remaps they drifted every time, each leaving a stale number in a table
that reads as authoritative -- which is worse than no table. This fails the
build instead of waiting for a reader to notice.

Checks only the facts that exist in both places. Run via `make check-pins`.
"""

import re
import sys
from pathlib import Path

CFG = Path("firmware/WhackAMole/Config.h")
DOC = Path("docs/wiring.html")


def config_pins(src):
    def arr(name):
        m = re.search(name + r"\[\w+\]\s*=\s*\{([^}]*)\}", src)
        if not m:
            sys.exit(f"could not find {name} in {CFG}")
        return [v.strip() for v in m.group(1).split(",")]

    m = re.search(r"kPixelDataPin\s*=\s*(\d+)", src)
    if not m:
        sys.exit(f"could not find kPixelDataPin in {CFG}")
    return arr("kP1ButtonPins"), arr("kP2ButtonPins"), m.group(1)


def doc_cell(doc, label):
    m = re.search(r"<tr><td>" + re.escape(label) + r"</td><td class=\"m\">([^<]*)</td>", doc)
    if not m:
        sys.exit(f"could not find the {label!r} row in {DOC}")
    return m.group(1).strip()


def ribbon_rows(doc):
    """Pull (pos, row, teensy, carries) out of the ribbon pinout table.

    Laid out two positions per <tr>, so each row yields two entries.
    """
    start = doc.index('<h3 class="sub-h">Ribbon pinout</h3>')
    seg = doc[start : doc.index("</table>", start)]
    out = []
    for tr in re.findall(r"<tr>(.*?)</tr>", seg, re.S):
        cells = [
            re.sub(r"<[^>]+>", "", c).strip()
            for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)
        ]
        if len(cells) == 8 and cells[0].isdigit():
            out.append(tuple(cells[0:4]))
            out.append(tuple(cells[4:8]))
    return sorted(out, key=lambda e: int(e[0]))


def check_ribbon(doc, p1, p2):
    """The ribbon's twelve live positions carry the switch pins in order.

    Positions 2 and 5 are the strips cut away from the Teensy -- they land on
    pin 10 (reserved) and 3.3 V -- and are reused for ground and pixel data.
    """
    bad = []
    entries = ribbon_rows(doc)
    if len(entries) != 14:
        return [f"  ribbon table has {len(entries)} positions, expected 14"]

    want_pins = p1 + p2  # P1 B R W G Y START, then P2
    live = iter(want_pins)
    for pos, row, pin, carries in entries:
        if int(row) != 20 + int(pos):
            bad.append(f"  ribbon pos {pos}: row {row}, expected {20 + int(pos)}")
        if pos in ("2", "5"):
            if pin != "\u2014":
                bad.append(f"  ribbon pos {pos}: expected no Teensy pin, doc says {pin!r}")
            continue
        want = next(live)
        if pin != want:
            bad.append(f"  ribbon pos {pos} ({carries}): doc says pin {pin}, Config.h says {want}")
    return bad


def check_chain_order(doc, p1, p2):
    """The "Chain order must match Config.h" table lists each cap's switch pin.

    It went stale through a remap without anything noticing, which is the
    reason it is checked now.
    """
    rows = {
        "1\u20135": ", ".join(p1[:5]),
        "6\u201310": ", ".join(p2[:5]),
        "\u2014": f"{p1[5]} \u00b7 {p2[5]}",
    }
    bad = []
    for first, want in rows.items():
        m = re.search(
            r'<tr><td class="m">' + first + r"</td><td>.*?</td><td class=\"m\">[^<]*</td>"
            r'<td class="m">([^<]*)</td></tr>',
            doc,
        )
        if not m:
            bad.append(f"  chain order table: could not find the {first!r} row")
        elif m.group(1).strip() != want:
            bad.append(f"  chain order {first}: doc says {m.group(1)!r}, Config.h says {want!r}")
    return bad


def main():
    p1, p2, pixel = config_pins(CFG.read_text())
    doc = DOC.read_text()

    # Config stores six pins per player: five caps then start.
    expect = {
        "Pixel data": pixel,
        "P1 buttons \u2014 B R W G Y": ", ".join(p1[:5]),
        "P1 start": p1[5],
        "P2 buttons \u2014 B R W G Y": ", ".join(p2[:5]),
        "P2 start": p2[5],
    }

    bad = []
    for label, want in expect.items():
        got = doc_cell(doc, label)
        if got != want:
            bad.append(f"  {label}: doc says {got!r}, Config.h says {want!r}")

    # The level shifter table names the pixel pin a second time.
    m = re.search(r"<td>Teensy pin <b>(\d+)</b>", doc)
    if not m:
        bad.append("  level shifter table: could not find the 'Teensy pin <n>' cell")
    elif m.group(1) != pixel:
        bad.append(f"  level shifter 1A: doc says pin {m.group(1)}, kPixelDataPin is {pixel}")

    bad += check_ribbon(doc, p1, p2)
    bad += check_chain_order(doc, p1, p2)

    if bad:
        print("docs/wiring.html has drifted from Config.h:\n" + "\n".join(bad))
        return 1
    print(f"pins OK \u2014 P1 {p1}  P2 {p2}  pixel {pixel}  (+ ribbon and chain tables)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
