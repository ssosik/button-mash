#!/usr/bin/env python3
"""Lay out the controller board from gen-netlist.py, using KiCad's own API.

Run with the Python that ships inside KiCad, which is the one that can import
pcbnew:

    /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3 \\
        hardware/controller-board/gen-pcb.py

then let KiCad check it against the schematic and fill the ground pours:

    kicad-cli pcb drc --schematic-parity --refill-zones --save-board \\
        hardware/controller-board/controller-board/controller-board.kicad_pcb

The placement copies the stripboard on purpose. The harness header sits
beside the Teensy's left row, a row apart from it, so twelve of the fourteen
harness positions are a straight trace to the Teensy pin opposite -- the PCB
version of "the strip is the wire". The two that are not (ground and the
shifted pixel data, in the places of the audio-reserved pin 10 and 3.3 V)
arrive from elsewhere, exactly as on the stripboard.

Ground is a pour on both layers. Everything else is a track placed here, in
millimetres from the board's top-left corner.
"""

import importlib.util
import pathlib
import sys

import pcbnew

HERE = pathlib.Path(__file__).resolve().parent
PROJECT = HERE / "controller-board"
PRETTY = PROJECT / "controller-board.pretty"
FOOTPRINTS = pathlib.Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")
MODELS = "${KICAD10_3DMODEL_DIR}"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


NL = _load("controller_netlist", HERE / "gen-netlist.py")
SCH = _load("controller_schematic", HERE / "gen-schematic.py")

# Board, in mm from its top-left corner. Placed on the page at ORIGIN.
W, H = 64.0, 76.0
ORIGIN = (100.0, 50.0)
PITCH = 2.54

# Teensy pad 1 (left row, USB end); the right row is 0.6" across.
TX, TY = 28.0, 10.0
TR = TX + 6 * PITCH  # 43.24

# Harness pin 1. Position k lines up with Teensy left-row pad k + 10.
HX, HY = 18.0, TY + 10 * PITCH

# 74AHCT125 pin 1; pins 1-7 run down, 8-14 back up the far side.
UX, UY = 5.5, 12.0
UX2 = UX + 3 * PITCH  # 13.12

SIGNAL, POWER = 0.4, 0.8


def mm(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(ORIGIN[0] + x), pcbnew.FromMM(ORIGIN[1] + y))


def teensy_y(pad):
    """Row y of a Teensy pad, either side."""
    return TY + ((pad - 1) % 24) * PITCH


def shifter_xy(pin):
    if pin <= 7:
        return UX, UY + (pin - 1) * PITCH
    return UX2, UY + (14 - pin) * PITCH


# --- The Teensy footprint ---------------------------------------------------


def teensy_footprint():
    """Two 24-pin rows for female headers, numbered as gen-netlist.py numbers them.

    Only the outer rows: the board takes 5 V on VIN and uses nothing on the
    Teensy's inner pads or its bottom. The 3D view shows the two sockets the
    Teensy sits in rather than the Teensy itself, which KiCad has no model of.
    """
    o = [
        '(footprint "Teensy41_Socketed" (version 20240108) (generator "gen-pcb.py")',
        '  (layer "F.Cu")',
        '  (descr "Teensy 4.1 on two 1x24 female headers, outer rows only.'
        ' Cut the VIN-VUSB pad when powering from VIN.")',
        '  (tags "Teensy 4.1 PJRC")',
        '  (property "Reference" "REF**" (at 7.62 -4.4 0) (layer "F.SilkS")'
        " (effects (font (size 1 1) (thickness 0.15))))",
        '  (property "Value" "Teensy41_Socketed" (at 7.62 61.5 0) (layer "F.Fab")'
        " (effects (font (size 1 1) (thickness 0.15))))",
        # The Teensy's own outline, 17.78 x 60.96 mm, and its USB connector.
        "  (fp_rect (start -1.27 -1.27) (end 16.51 59.69)"
        ' (stroke (width 0.12) (type solid)) (fill none) (layer "F.SilkS"))',
        "  (fp_rect (start 3.81 -2.54) (end 11.43 2.54)"
        ' (stroke (width 0.12) (type solid)) (fill none) (layer "F.SilkS"))',
        '  (fp_text user "USB" (at 7.62 0 0) (layer "F.SilkS")'
        " (effects (font (size 1 1) (thickness 0.15))))",
        '  (fp_text user "TEENSY 4.1" (at 7.62 22 90) (layer "F.SilkS")'
        " (effects (font (size 1.5 1.5) (thickness 0.2))))",
        '  (fp_text user "CUT VIN-VUSB" (at 7.62 40 90) (layer "F.SilkS")'
        " (effects (font (size 1 1) (thickness 0.15))))",
        "  (fp_rect (start -1.52 -2.79) (end 16.76 59.94)"
        ' (stroke (width 0.05) (type solid)) (fill none) (layer "F.CrtYd"))',
        "  (fp_rect (start -1.27 -1.27) (end 16.51 59.69)"
        ' (stroke (width 0.1) (type solid)) (fill none) (layer "F.Fab"))',
    ]
    for pad in range(1, 49):
        x = 0 if pad <= 24 else 6 * PITCH
        y = ((pad - 1) % 24) * PITCH
        shape = "rect" if pad == 1 else "circle"
        o.append(
            f'  (pad "{pad}" thru_hole {shape} (at {x:.2f} {y:.2f}) (size 1.7 1.7)'
            ' (drill 1.0) (layers "*.Cu" "*.Mask"))'
        )
    for x in (0, 6 * PITCH):
        o.append(
            f'  (model "{MODELS}/Connector_PinSocket_2.54mm.3dshapes/'
            'PinSocket_1x24_P2.54mm_Vertical.step"'
            f" (offset (xyz {x:.2f} 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))"
        )
    o.append(")")
    PRETTY.mkdir(parents=True, exist_ok=True)
    (PRETTY / "Teensy41_Socketed.kicad_mod").write_text("\n".join(o) + "\n")


# --- Placement --------------------------------------------------------------

# ref -> (x, y, rotation). Rotation -90 turns a connector's pin row from
# left-to-right into top-to-bottom.
PLACEMENT = {
    NL.U1: (TX, TY, 0),
    NL.U2: (UX, UY, 0),
    NL.J1: (HX, HY, 0),
    # Pin 1 (ground) level with the Teensy's ground pin, then RX and TX level
    # with pins 0 and 1: the serial traces are as short as they can be.
    NL.J2: (21.0, TY, -90),
    NL.J3: (56.0, 14.0, -90),
    NL.C1: (50.0, 26.0, -90),
    NL.C2: (UX + 2.62, 8.5, 0),
    "H1": (4.0, 4.0, 0),
    "H2": (W - 4.0, 4.0, 0),
    "H3": (4.0, H - 4.0, 0),
    "H4": (W - 4.0, H - 4.0, 0),
}


# Reference designators moved off their library default where it collides:
# J2's would sit on the pin labels, U2's on the decoupling cap.
REF_AT = {
    NL.J2: (16.0, TY + 2.5, 90),
    NL.U2: (UX + 3.81, UY + 3 * PITCH, 90),
    NL.J3: (57.5, 23.6, 0),
}

# KiCad 10's MX126 footprint names a 3D model the library does not ship. The
# Phoenix MKDS 1,5 is the same 5 mm pitch and near enough the same body; as on
# the button board, it stands in so the 3D view does not show bare pads.
MODEL_STANDIN = {
    "TerminalBlock_MaiXu_MX126-5.0-02P_1x02_P5.00mm": MODELS
    + "/TerminalBlock_Phoenix.3dshapes/"
    + "TerminalBlock_Phoenix_MKDS-1,5-2_1x02_P5.00mm_Horizontal.step",
}


def load_footprint(fpid):
    lib, name = fpid.split(":")
    path = PRETTY if lib == "controller-board" else FOOTPRINTS / f"{lib}.pretty"
    fp = pcbnew.FootprintLoad(str(path), name)
    if fp is None:
        sys.exit(f"footprint {fpid} not found in {path}")
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    if name in MODEL_STANDIN:
        # Index rather than iterate: iterating a SWIG vector yields copies,
        # and editing a copy changes nothing.
        models = fp.Models()
        for i in range(len(models)):
            models[i].m_Filename = MODEL_STANDIN[name]
    return fp


def open_net_name(ref, pad):
    """The name KiCad's schematic gives a pin left open, which the pad must carry
    for the schematic-parity check to pass: unconnected-(REF-PINNAME-PadN).
    """
    name = NL.TEENSY_PINS[int(pad) - 1] if ref == NL.U1 else ""
    return f"unconnected-({ref}-{name}-Pad{pad})" if name else f"unconnected-({ref}-Pad{pad})"


def place(board, comps, nets):
    netinfo = {}
    for name in nets:
        item = pcbnew.NETINFO_ITEM(board, "/" + name)
        board.Add(item)
        netinfo[name] = item
    pad_net = {(ref, str(pin)): name for name, nodes in nets.items() for ref, pin in nodes}

    for ref, value, fpid, note in comps:
        fp = load_footprint(fpid)
        x, y, rot = PLACEMENT[ref]
        fp.SetReference(ref)
        fp.SetValue(value)
        fp.SetPosition(mm(x, y))
        fp.SetOrientationDegrees(rot)
        # Links the footprint to its schematic symbol: the same UUID the
        # schematic generator derives, so DRC's parity check can pair them.
        fp.SetPath(pcbnew.KIID_PATH("/" + SCH.sym_uuid(ref)))
        fp.SetField("Note", note)
        fp.GetField("Note").SetVisible(False)
        if ref in REF_AT:
            x, y, angle = REF_AT[ref]
            fp.Reference().SetPosition(mm(x, y))
            fp.Reference().SetTextAngleDegrees(angle)
        elif ref.startswith("H"):
            fp.Reference().SetVisible(False)  # a hole needs no label at the edge
        board.Add(fp)
        for pad in fp.Pads():
            if not pad.GetNumber():
                continue
            name = pad_net.get((ref, pad.GetNumber()))
            if name:
                pad.SetNet(netinfo[name])
            else:
                item = pcbnew.NETINFO_ITEM(board, open_net_name(ref, pad.GetNumber()))
                board.Add(item)
                pad.SetNet(item)
    return netinfo


# --- Routing ----------------------------------------------------------------


def track(board, net, points, width, layer):
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(mm(x0, y0))
        t.SetEnd(mm(x1, y1))
        t.SetWidth(pcbnew.FromMM(width))
        t.SetLayer(layer)
        t.SetNet(net)
        board.Add(t)


def route(board, nets, netinfo):
    F, B = pcbnew.F_Cu, pcbnew.B_Cu
    teensy = {(ref, pin): name for name, nodes in nets.items() for ref, pin in nodes}

    # Harness: twelve straight runs, header pin to the Teensy pad level with it.
    for pos in range(1, 15):
        name = teensy[(NL.J1, pos)]
        if not name.startswith("SW_"):
            continue
        y = HY + (pos - 1) * PITCH
        track(board, netinfo[name], [(HX, y), (TX, y)], SIGNAL, F)

    # Serial: J2 pins 2 and 3 at 2.5 mm pitch to Teensy pads at 2.54 -- a
    # 0.04 mm skew over 7 mm, so a straight run is fine.
    for pin, pad in ((2, NL.teensy_pad(NL.SERIAL_RX)), (3, NL.teensy_pad(NL.SERIAL_TX))):
        name = teensy[(NL.J2, pin)]
        track(board, netinfo[name], [(21.0, TY + (pin - 1) * 2.5), (TX, teensy_y(pad))], SIGNAL, F)

    # Pixel data in: Teensy pin 8 left, above the harness header, then up
    # between the shifter's two pin rows to 1A.
    pin8_y = teensy_y(NL.teensy_pad(NL.PIXEL_PIN))
    a1 = shifter_xy(NL.SHIFTER["1A"])
    lane = (UX + UX2) / 2 - 0.2
    track(board, netinfo["PIXEL_3V3"], [(TX, pin8_y), (lane, pin8_y), (lane, a1[1]), a1], SIGNAL, F)

    # Pixel data out: 1Y down the board's left edge, underneath, and across
    # to harness position 5 -- the 3.3 V row's place on the stripboard.
    y1 = shifter_xy(NL.SHIFTER["1Y"])
    pos5_y = HY + 4 * PITCH
    track(board, netinfo["PIXEL_5V"], [y1, (2.6, y1[1]), (2.6, pos5_y), (HX, pos5_y)], SIGNAL, B)

    # +5 V, top side: terminal to VIN, and down to the bulk capacitor.
    p5 = netinfo["+5V"]
    j3 = (56.0, 14.0)
    vin_y = teensy_y(NL.teensy_pad("VIN"))
    track(board, p5, [j3, (50.0, j3[1]), (50.0, vin_y), (TR, vin_y)], POWER, F)
    track(board, p5, [(50.0, j3[1]), (50.0, 26.0)], POWER, F)
    # Decoupling cap straight onto the '125's VCC pin.
    vcc = shifter_xy(NL.SHIFTER["VCC"])
    track(board, p5, [(UX2, 8.5), vcc], POWER, F)

    # +5 V, underneath: along the top edge above the Teensy, then down the
    # shifter's right side to VCC and the three OE pins that hold gates 2-4 off.
    bus_x = UX2 + 2.5
    track(board, p5, [j3, (j3[0], 6.0), (bus_x, 6.0), (bus_x, shifter_xy(10)[1])], POWER, B)
    for pin in ("VCC", "4OE", "3OE"):
        x, y = shifter_xy(NL.SHIFTER[pin])
        track(board, p5, [(bus_x, y), (x, y)], SIGNAL, B)
    # 2OE is on the far row: cross under the chip between pins 10 and 11.
    oe2 = shifter_xy(NL.SHIFTER["2OE"])
    gap_y = oe2[1] + PITCH / 2
    track(board, p5, [(bus_x, gap_y), (UX + 2.1, gap_y), (UX + 2.1, oe2[1]), oe2], SIGNAL, B)


def outline(board):
    rect = pcbnew.PCB_SHAPE(board)
    rect.SetShape(pcbnew.SHAPE_T_RECT)
    rect.SetStart(mm(0, 0))
    rect.SetEnd(mm(W, H))
    rect.SetLayer(pcbnew.Edge_Cuts)
    rect.SetWidth(pcbnew.FromMM(0.1))
    board.Add(rect)


def ground_pours(board, netinfo):
    inset = 0.5
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        zone = pcbnew.ZONE(board)
        zone.SetLayer(layer)
        zone.SetNet(netinfo["GND"])
        poly = zone.Outline()
        poly.NewOutline()
        for x, y in (
            (inset, inset),
            (W - inset, inset),
            (W - inset, H - inset),
            (inset, H - inset),
        ):
            p = mm(x, y)
            poly.Append(p.x, p.y)
        zone.SetMinThickness(pcbnew.FromMM(0.25))
        zone.SetThermalReliefGap(pcbnew.FromMM(0.4))
        zone.SetThermalReliefSpokeWidth(pcbnew.FromMM(0.5))
        zone.SetLocalClearance(pcbnew.FromMM(0.3))
        zone.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        board.Add(zone)


def silkscreen(board):
    def text(s, x, y, size=1.0, angle=0, justify=None):
        t = pcbnew.PCB_TEXT(board)
        t.SetText(s)
        t.SetPosition(mm(x, y))
        t.SetLayer(pcbnew.F_SilkS)
        t.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(size), pcbnew.FromMM(size)))
        t.SetTextThickness(pcbnew.FromMM(size * 0.15))
        t.SetTextAngleDegrees(angle)
        if justify == "right":
            t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_RIGHT)
        elif justify == "left":
            t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT)
        board.Add(t)

    text("WHACK-A-MOLE ATTACK - CONTROLLER", W / 2, H - 4.6, 1.2)
    text("rev A   2026-10-30", W / 2, H - 2.6, 1.0)
    text("TO BUTTON BOARD J13", HX - 2.6, HY + 6.5 * PITCH, 1.0, 90)
    # Pin by pin, from the Teensy's side: the cable crosses RX and TX over.
    text("TO PORTAL", 21.0, 3.6, 0.9)
    text("1 GND  2 RX  3 TX", 21.0, 5.4, 0.8)
    # Outboard of the terminal body, which reaches x = 61.3.
    text("+5V", 62.9, 14.0, 0.9, 90)
    text("GND", 62.9, 19.0, 0.9, 90)
    text("5V IN", 56.0, 9.2, 0.9)


def main():
    comps, nets = NL.build()
    problems = NL.validate(comps, nets)
    if problems:
        print("refusing to lay out an inconsistent netlist:", file=sys.stderr)
        for p in problems:
            print("  " + p, file=sys.stderr)
        return 1
    teensy_footprint()

    path = PROJECT / "controller-board.kicad_pcb"
    board = pcbnew.NewBoard(str(path))
    ds = board.GetDesignSettings()
    ds.SetCopperLayerCount(2)
    ds.m_CopperEdgeClearance = pcbnew.FromMM(0.5)

    netinfo = place(board, comps, nets)
    route(board, nets, netinfo)
    outline(board)
    ground_pours(board, netinfo)
    silkscreen(board)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(str(path))
    print(f"wrote {path.relative_to(HERE.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
