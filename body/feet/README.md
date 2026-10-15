# Feet: foot-contact switches

Each foot gets a Cylewet lever micro-switch so krēCHer knows which feet are on the ground
(all six closed when standing; lifting a leg opens its switch). Wiring: COM → signal on one of
the Servo 2040's six sensor headers, NO → 3.3 V (foot down reads ~3.3 V).

**Status: concept.** Nothing printed yet; sizes in the drawings are placeholders until the leg
and switch are measured.

## Design

The foot is a 3D-printed cap that bolts onto the end of the aluminium lower leg through the
leg's existing holes. A plunger slides in the cap: when the foot lands it moves up about
1.5 mm and clicks the switch, then a collar bottoms out on the cap at about 2.5 mm. From there
the robot's weight goes into the plastic, never into the switch. Idea adapted from Robot Lk's
"Build an 18DOF Hexapod Robot", Part 4 (limit switch setup, ~11:35).

| Drawing | What it shows |
| --- | --- |
| [`foot_switch_cap_v0.svg`](foot_switch_cap_v0.svg) | v0: the cap with a round toe |
| [`foot_switch_heel_v1.svg`](foot_switch_heel_v1.svg) | v1, chosen: krēCHer in heels. The plunger ends in a doll-foot peg glued into a toy crystal high heel (~30 × 12 × 10 mm) |
| [`foot_switch_syringe_v2.svg`](foot_switch_syringe_v2.svg) | v2, prototype without a 3D printer: a 3–5 ml syringe is the housing and plunger, zip-tied beside the leg tip; thread tethers keep the plunger from dropping out; the heel glued to the thumb pad |
| [`foot_switch_pen_v3.svg`](foot_switch_pen_v3.svg) | v3: clicky-pen ankle. A retractable pen's barrel (cut to ~45 mm) clips onto the leg tip; its chrome button is the ankle, its spring resets the foot, a skewer pushes the switch on top; a washer on the button is the hard stop |
| [`foot_switch_pen_v4.svg`](foot_switch_pen_v4.svg) | v4: v3's pen mechanism dressed in two Sharpie grip tubes. The spiral grip (slit on the leg side) is the calf skin, the plain grip is a boot hiding the travel gap, and rings sliced from it are the sole pads. The rubber never carries weight |
| [`foot_switch_pen_v5.svg`](foot_switch_pen_v5.svg) | v5: the switch stands in a window cut in the grip's side, its wire lever bent 90° through a slot into the barrel. The spring is glued to a plug and to the chrome stem that carries the heel, on a skewer guide pin; a washer on the stem is the hard stop. The rubber is skin only |
| [`foot_switch_v6_band.svg`](foot_switch_v6_band.svg) | v6: from Mawa's mock-up. One grip tube over two short wood dowels; the switch slides crosswise through a slit at the joint and shows like an ankle band. The lower dowel lifts the lever, then meets the upper one (2.5 mm hard stop). An unglued stretch of rubber is the spring. Adds ~4 cm to the leg |
| [`foot_switch_v7_putty.svg`](foot_switch_v7_putty.svg) | v7: v6 with two-part epoxy putty instead of wood. The upper core is cast around the scuffed leg tip (putty through the leg holes locks it on, no bolt); the switch is bedded in the putty; the filled heel and the lower core are one putty piece, glued into the grip at its bottom only with E6000 |
| [`foot_switch_v8_tendon.svg`](foot_switch_v8_tendon.svg) | v8: v7 plus the pen's spring as an Achilles tendon up the back of the ankle (hooked ends set in the upper putty and in a putty bump on the heel, squashed 2–3 mm). It returns the heel, so only ~5 mm of rubber is left free and the heel tilts less |
| [`foot_switch_v9_stack.svg`](foot_switch_v9_stack.svg) | v9: Mawa's stack, top to bottom: switch → wall anchor → grip → spring → heel. A putty "knee" holds the leg tip, the anchor's flange and the switch. The anchor is a fixed shin bone inside the grip; the grip, the putty plug and the heel slide up together over it, the rim lifts the switch lever, and the heel's putty stops against the anchor's tip. The pen spring (cut to ~12 mm) in a pocket in the plug pushes it back |
| [`foot_switch_v10_gluestick.svg`](foot_switch_v10_gluestick.svg) | v10: a ~20 mm piece of hot-glue stick replaces the wall anchor as the fixed shin bone (hot-glued to the leg tip, thread-wrapped, packing tape so the grip slides). The switch sits in a slit in the grip's side and rides with it; its bent lever tip meets the stick's end. The spring (cut to ~12 mm) is hot-glued into pockets in the stick and the hot-glue-filled heel, so it also holds the heel on |
| [`foot_switch_v11_bolted.svg`](foot_switch_v11_bolted.svg) | v11: the grip's narrow end goes straight over the leg tip and is held by an M3 bolt through the rubber and the leg's first hole, so the grip and switch are fixed. A tape-wrapped glue stick is the plunger, with the heel glued to its bottom and a disc on top; the spring (cut to ~12 mm) is glued between the leg's end and a pocket in the stick. The disc lifts the switch lever, then stops against the leg's end |
| [`foot_switch_v12_flush.svg`](foot_switch_v12_flush.svg) | v12, current: v11 with the whole switch tucked into the slit, between the leg's flat side and the rubber, its bottom level with the leg's end (lever tip bent under it, so the disc stops on the leg before it can touch the switch). The bolt moves to the leg's second hole, and the glue-stick plunger is ~12 mm |

![krēCHer in heels, concept v1](foot_switch_heel_v1.svg)

## Making the heel work

- Fill each shoe solid with two-part epoxy putty (not hot glue: it creeps under weight), so it isn't a hollow shell.
- Rubber dots under the heel tip and the ball of the foot for grip.
- A flat on the plunger shaft so the shoe always points forward.

## Next

- [ ] Load test: one filled shoe standing on its heel under ~1 kg (a 1 L bottle), rocked like a
      landing. If it cracks, use the v0 round toe and keep the shoe as decoration.
- [ ] Measure: leg thickness and width at the tip, hole size and spacing, last hole to tip;
      switch body size, its mounting holes, where the lever clicks; the shoe's opening.
- [ ] Pen ankle (v3): check the button can't slide out, slides freely without the click cam, and the clip fits the leg; then dry-fit one foot on one leg.
- [ ] Final six: laser-cut acrylic stack (2D cut files) or a parametric OpenSCAD model → fit-test print → one foot on one leg → all six.
- [ ] Update the leg length in the gait code (the cap adds ~3–4 cm).
