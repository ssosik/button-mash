// Whack A Mole Attack -- WS2812 ring carrier for a 60mm dome arcade button
//
// Replaces the single 5mm LED in the generic 60mm dome button (Adafruit 1190 /
// EG STARTS class) with an Adafruit 1643 12-pixel NeoPixel ring mounted in the
// plunger's underside cavity, directly behind the dome.
//
// Two printed parts:
//
//   ring_seat  A stepped annulus that friction-fits the plunger cavity. Its
//              outer rib fills the gap between the ring and the cavity wall; a
//              thin lip at the bottom retains the ring against the dome.
//
//   bore_plug  Replaces the stock LED holder in the switch bracket. The ring's
//              four wires come down the hollow stem and out through this plug,
//              so the only flex is across the plunger's 3mm travel, entirely
//              inside the stem where the spring cannot reach them.
//
// Wire route:  ring pads -> radially inward across the gap between the ring ID
//              and the stem OD -> straight down the stem bore -> bore plug.
//              Nothing passes under the ring and the stem is never drilled.
//
// Every measured dimension is a variable below. If a test print binds or
// rattles, change the *_clearance value, not the measurement.
//
// Print: PETG, 0.2mm layers, 100% infill. Seat prints pocket-up (the retaining
// lip is then the first two layers, flat on the bed). Plug prints flange-down.

// What to render: "seat", "plug", or "both"
part = "both";

// --------------------------------------------------------------------------
// Measured from the button with calipers
// --------------------------------------------------------------------------
cavity_id      = 45.0;  // plunger underside cavity, inner diameter
cavity_depth   =  4.0;  // dome underside to cavity rim
stem_od        = 18.5;  // hollow stem, outside
bore_id        = 10.5;  // hollow stem, inside
socket_id      = 10.3;  // LED holder socket in the microswitch bracket
plunger_travel =  3.0;  // rest to fully pressed
socket_depth   =  2.0;  // TODO: measure bracket thickness at the socket

// --------------------------------------------------------------------------
// Adafruit 1643 NeoPixel Ring, 12 x 5050.
//
// Height is MEASURED at 2.5-3.0mm. Published figures disagree and are both
// wrong: the 1643 product page says 6.7mm (would not fit this cavity at all)
// and the NeoPixel Uberguide says 3.6mm.
//
// Deliberately set to the TOP of the measured range. Erring high just leaves
// the ring a little loose under the lip, and a small air gap behind the dome
// diffuses better anyway. Erring low makes the ring stand proud of the cavity,
// which stops the seat sitting flush and fouls the press.
// --------------------------------------------------------------------------
ring_od     = 36.8;
ring_id     = 23.3;
ring_height =  3.0;

// --------------------------------------------------------------------------
// Wire. 30 AWG silicone is ~1.0mm. Four conductors: 5V, GND, DIN, DOUT.
// --------------------------------------------------------------------------
wire_od    = 1.0;
wire_count = 4;

// --------------------------------------------------------------------------
// Print fit. Tune these after the first test print.
// --------------------------------------------------------------------------
seat_fit_clearance    = 0.3;  // subtracted from cavity_id; light friction fit
ring_pocket_clearance = 0.4;  // added to ring_od so the ring drops in
lip_overlap           = 1.4;  // how far the retaining lip reaches under the ring
plug_press_fit        = 0.1;  // added to socket_id; interference in the bracket
plug_bore_clearance   = 0.6;  // subtracted from bore_id; stem must slide freely

$fn = 128;

// --------------------------------------------------------------------------
// Derived
// --------------------------------------------------------------------------
seat_od   = cavity_id - seat_fit_clearance;
seat_h    = cavity_depth - 0.1;             // never proud of the cavity rim
pocket_d  = ring_od + ring_pocket_clearance;
lip_t     = cavity_depth - ring_height;     // all the room the ring leaves
lip_id    = ring_od - 2 * lip_overlap;
rib_h     = seat_h - lip_t;

plug_socket_od = socket_id + plug_press_fit;
plug_bore_od   = bore_id - plug_bore_clearance;
plug_hollow    = 6.0;                       // room for four wires with slack
plug_insert_h  = 8.0;                       // how far the plug reaches up the bore
plug_flange_d  = 15.0;
plug_flange_h  = 3.5;                       // thick enough to tunnel a zip tie
tie_w          = 3.0;                       // zip tie strap width
tie_t          = 1.4;                       // zip tie strap thickness, with clearance

// --------------------------------------------------------------------------
// Sanity checks. These fail loudly in the OpenSCAD console rather than letting
// you print something that cannot work.
// --------------------------------------------------------------------------
assert(ring_id > stem_od + 2.0,
  str("Ring ID ", ring_id, " leaves no room beside the ", stem_od, "mm stem ",
      "for the wires to reach the bore"));

assert((ring_id - stem_od) / 2 >= wire_od,
  str("Gap between ring ID and stem is ", (ring_id - stem_od) / 2,
      "mm; one ", wire_od, "mm wire will not pass. Use thinner wire."));

assert(pocket_d < cavity_id - 2 * 1.5,
  "Ring too large: the seat's outer rib would be under 1.5mm thick");

assert(lip_t >= 0.3,
  str("Ring is too tall for the cavity: only ", lip_t, "mm left for the ",
      "retaining lip. Measure ring_height."));

assert(plug_socket_od < bore_id,
  "Plug's socket section is wider than the stem bore and would bind the plunger");

assert(plug_bore_od > plug_hollow + 2 * 1.2,
  "Plug wall would be under 1.2mm; shrink plug_hollow");

assert(plug_hollow >= wire_count * wire_od,
  str("Plug hollow ", plug_hollow, "mm is too tight for ", wire_count,
      " wires of ", wire_od, "mm"));

// --------------------------------------------------------------------------
// Ring seat
//
// Two concentric steps. The lip gets whatever height the ring leaves in the
// 4mm cavity -- 1.0mm as measured. It is a continuous annulus backed by the
// rib, reaches only lip_overlap inward, and carries a 3.3g ring, so it is in
// no danger. It prints flat on the bed as the first few layers.
// --------------------------------------------------------------------------
module ring_seat() {
  difference() {
    union() {
      // Retaining lip: the full annulus at the bottom.
      cylinder(d = seat_od, h = lip_t);
      // Outer rib: fills the gap between ring and cavity wall, and is the
      // friction-fit surface.
      translate([0, 0, lip_t])
        cylinder(d = seat_od, h = rib_h);
    }
    // Ring pocket, open at the top.
    translate([0, 0, lip_t])
      cylinder(d = pocket_d, h = rib_h + 1);
    // Central opening: everything inside the lip is clear, so the wires drop
    // straight through toward the stem bore.
    translate([0, 0, -1])
      cylinder(d = lip_id, h = lip_t + 2);
  }
}

// --------------------------------------------------------------------------
// Bore plug
// --------------------------------------------------------------------------
module bore_plug() {
  total_h = plug_flange_h + socket_depth + plug_insert_h;

  difference() {
    union() {
      // Flange: stops against the underside of the bracket.
      cylinder(d = plug_flange_d, h = plug_flange_h);
      // Socket section: interference fit where the LED holder used to be.
      translate([0, 0, plug_flange_h])
        cylinder(d = plug_socket_od, h = socket_depth);
      // Bore section: narrower, reaches up into the stem with clearance so the
      // plunger slides over it freely.
      translate([0, 0, plug_flange_h + socket_depth])
        cylinder(d = plug_bore_od, h = plug_insert_h);
    }

    // Through-hollow for the wires.
    translate([0, 0, -1]) cylinder(d = plug_hollow, h = total_h + 2);

    // Flared mouth at the top so the wires bend over a radius, not an edge.
    translate([0, 0, total_h - 1.5])
      cylinder(d1 = plug_hollow, d2 = plug_hollow + 2.4, h = 1.51);

    // Chamfer at the bottom exit too.
    translate([0, 0, -0.01])
      cylinder(d1 = plug_hollow + 1.6, d2 = plug_hollow, h = 0.8);

    // Strain relief: a tunnel running tangentially through the flange, beside
    // the hollow. A zip tie threads through it, wraps the wire bundle where it
    // exits below, and the flange is the bar it cinches against. Any pull on
    // the connector ends here, not at the solder joints on the ring.
    translate([plug_hollow / 2 + 1.0, -plug_flange_d / 2 - 1, (plug_flange_h - tie_t) / 2])
      cube([tie_w, plug_flange_d + 2, tie_t]);
  }
}

// --------------------------------------------------------------------------
// Layout
// --------------------------------------------------------------------------
if (part == "seat" || part == "both") {
  ring_seat();
}
if (part == "plug" || part == "both") {
  translate([part == "both" ? seat_od / 2 + plug_flange_d / 2 + 6 : 0, 0, 0])
    bore_plug();
}

// --------------------------------------------------------------------------
// Assembly
// --------------------------------------------------------------------------
//
//  1. Pull the stock LED holder out of the bracket socket and discard it.
//
//  2. Solder four 30 AWG silicone wires to the ring's back pads: 5V, GND, DIN,
//     DOUT. Lay them flat and run them INWARD toward the centre hole. Keep the
//     joints low -- only lip_t of height exists below the ring.
//
//  3. Drop the ring into the seat's pocket, LEDs facing OUT of the pocket (they
//     face the dome once installed), wires gathered through the centre.
//
//  4. Feed the wire bundle down the stem bore, then push the seat up into the
//     plunger cavity until the rib is flush with the rim.
//
//  5. Push the bore plug up into the bracket socket from below, feeding the
//     wires through its hollow. Leave a service loop inside the stem: the
//     plunger travels 3mm, so the wires need at least that much slack.
//
//  6. Thread a small zip tie through the tunnel in the plug flange, wrap it
//     round the bundle where it exits underneath, and cinch.
//
//  7. Reassemble the spring and switch. Press the plunger through full travel
//     by hand and confirm nothing catches before it goes back in the table.
