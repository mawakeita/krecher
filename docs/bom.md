# krēCHer — Hardware Bill of Materials

**Project:** krēCHer — Small Linux Devices, LLMs, and Embodied Remote Presence
**Courses:** PSAM 5600 B — Currents: Small Devices, Large Language Models (Prof. David Carroll) · PGTE 5900 Independent Study (Prof. Thiago Hersan)
**Term:** Fall 2026
**Primary computing platform:** Raspberry Pi 5 (8GB)
**Final demo:** November 18, 2026 (full body: walking, head on body, skin on)
**Body assembly target:** October 7, 2026 (midterm pitch)
**Last updated:** October 1, 2026

---

## 1. Overview

krēCHer is an experimental embodied computing project exploring how a small Linux computer can be transformed into a physical, interactive creature.

**SENSE → COMPUTE → REACT → CONNECT → REMOTE PRESENCE**

The Raspberry Pi 5 is the onboard computer. It sits inside krēCHer's **head**, together with a SunFounder Fusion HAT+ that provides head movement, a camera, a speaker and a microphone. The hexapod **body** (Servo 2040 + MG996R servos + aluminum frame) is the next major build.

Detailed head notes (GPIO reservations, servo specs, power warnings) are in [`notes/bom_update_head_and_expression.md`](../notes/bom_update_head_and_expression.md).

---

## 2. Computing

| Component | Qty. | Cost | Status | Purpose |
| --- | ---: | ---: | --- | --- |
| Raspberry Pi 5, 8GB | 1 | $249.99 | **In use** | Onboard computer, mounted in the head |
| 128GB microSD card | 1 | Included | **In use** | Operating system and local storage |
| Raspberry Pi USB-C power supply | 1 | Included | **In use** | Plugs into the Fusion HAT+ (not the Pi) to charge the head battery and run the Pi |
| Active cooling case | 1 | Included | **Removed** | Case tray left off so the Pi can mount in the head; the Pi keeps a heatsink |

The microSD card, power supply and cooling case came with the Raspberry Pi starter kit and are not counted separately.

**Off-board compute (not owned):** a GPU machine from the class's D12 lab checkout (RTX 5070 Ti, 16 GB), reached over Tailscale for language-model reactions. See [`model_benchmarks.md`](model_benchmarks.md).

---

## 3. Head (SunFounder AI Fusion Lab Kit)

| Component | Qty. | Cost | Status | Purpose |
| --- | ---: | ---: | --- | --- |
| SunFounder AI Fusion Lab Kit (kit only) | 1 | $98.99 (list price) | **Acquired** | Head, vision, voice, expression, extra sensing |
| Fusion HAT+ | 1 | In kit | **Working** | Stacks on the Pi's GPIO header; drives head servos; speaker + mic |
| Fusion HAT+ battery (2S, 6.0–8.4V) | 1 | In kit | **Working** | Powers the head (Pi + HAT) via the HAT's power button |
| Pan-tilt mount + 2 SF006PRO servos | 1 | In kit | **Working** | Camera movement. Pan = PWM 2, tilt = PWM 3 |
| Camera: 5MP OV5647 + kit ribbon cable | 1 | In kit | **Working** | Vision; kit cable fits the Pi 5 |
| Two-level acrylic base + standoffs | 1 | In kit | **In use** | Temporary head structure: battery below, Pi + HAT above, pan-tilt on top |
| OLED screen, WS2812 RGB, ultrasonic, PIR, touch module, joystick | 1 each | In kit | **Acquired** | Face, mood light, extra sensing, input |
| PinPal pin-label board | 1 | In kit | **Acquired** | Pin identification |

**Head safety:** the 3S LiPo must **never** be connected to the Fusion HAT+. The HAT only takes its own 2S battery or USB-C.

**Kit overlaps (left unused):** the kit's 10-axis IMU duplicates the BNO085; its micro-switches duplicate the Cylewet switches; its relay duplicates the Ferwooh modules.

---

## 4. Sensors

| Component | Qty. | Cost | Status | Purpose |
| --- | ---: | ---: | --- | --- |
| Cylewet 3-pin SPDT lever micro-switches | 25 | $6.99 | **Tested (Exp. 01)** | Detect pressure/actuation. **6 reserved as foot-contact switches**, one per foot |
| Adafruit BNO085 IMU, Product 4754 | 1 | $29.50 | **Working (Exp. 02)** | Orientation, movement, acceleration and rotation |
| Camera, mic, touch, ultrasonic, PIR | — | In kit | See Section 3 | Vision, hearing and extra sensing from the head kit |

**Experiment 01 — done:** micro-switch → Raspberry Pi → digital response (tested across plate, fabric and light conditions).

**Experiment 02 — done:** BNO085 → Raspberry Pi → head movement. Kit cable to the Fusion HAT+ I2C port (no soldering); BNO085 at 0x4A, HAT at 0x17. 1,500-reading logged trial with 0 errors; the camera head follows the sensor.

**Independent study use:** these sensors are the data sources for detecting higher-level events (picked up, shaken, touched, approached…).

---

## 5. Body: robotics and mechanical movement

| Component | Qty. | Cost | Status | Purpose |
| --- | ---: | ---: | --- | --- |
| MG996R digital metal-gear servos (first 8) | 8 | $33.98 total | **Tested: 8/8 pass** | Hexapod leg joints |
| MG996R servos (3 Hosyond four-packs) | 12 | ~$51 | **Tested Oct 2: 12/12 pass** | Remaining leg joints + 2 spares (20 total) |
| Pimoroni Servo 2040, 18-channel | 1 | $38.94 | **Working on USB**: MicroPython v1.29.0-2, `servo2040 OK 18` | Leg servo controller; connects to the Pi by USB. **Before running servos above 5 V, cut the "Separate USB and Ext. Power" trace on the back.** Screw terminals: 10 A max continuous, so cap the buck converter at ~8–9 A with all 18 servos |
| 18-DOF aluminum hexapod frame | 1 | [not documented] | **Acquired**; parts identified | Mechanical body |
| 25T aluminium round servo horns, MG995/996 | 20 | [TBD] | **Arrived Oct 1**; fit the body plate (hub on the servo, flat face to the plate) | One per joint (18) + 2 spares |
| 30 cm servo extension cables (10-pack) | 1 | [TBD] | **Arrived Oct 1** | Leg servo wiring |
| Digital servo tester (HJ, 4 outputs) | 1 | $10.98 | **In use** | Test each servo before it goes into a leg; powered from the buck converter |

The Servo 2040's 18 channels are reserved for the legs. The head is driven separately by the Fusion HAT+.

**MG996R notes:** each weighs about 55 g (about 1 kg for 18) and can draw up to about 2.5 A when straining, so 18 moving together can exceed 10 A. Quality varies between sellers, so every servo is tested before assembly.

---

## 6. Power and electronics

| Component | Qty. | Cost | Status | Purpose |
| --- | ---: | ---: | --- | --- |
| OVONIC 3S 11.1V 2200mAh 120C LiPo | 2-pack | $36.99 | **Checked** | Body/leg servo power only. XT60 main plug. Both packs at storage charge (3.77–3.80 V/cell) |
| LiPo voltage checker | 1 | Included | **Included** | Battery voltage monitoring |
| Deans/T-plug connectors with 14AWG wire | 2 packs × 5 pairs | $10.99+ | **Acquired** | Downstream power wiring (the LiPos themselves use XT60) |
| ANMBEST CC/CV buck converter | 1 | $9.99 | **Set to 5.80 V** | Steps the 3S LiPo down to servo voltage. 6–40V in, 1.2–36V out, 0–20A current limit, 300W. Plan on ~15A continuous; CC limit as a fuse (~3A) for bench tests. OUT− is next to the blue screws |
| Ferwooh 5V relay modules | 3 | $5.98 | **Acquired** | Future switching experiments |
| MILAKE XT60 pigtail set, 12AWG | 6 pcs | $9.79 | **In use** | LiPo → buck converter input |
| SkyRC iMAX B6AC V2 balance charger | 1 | $84.99 | **Arrived** | Charges and balances the 3S LiPos; storage mode |
| AstroAI digital multimeter | 1 | $14.59 | **In use** | Set and check the buck converter output |
| Zeee LiPo Safe Bag (28×22 cm) | 1 | $6.29 | **In use** | Charging and storage for the 3S packs |

**Power architecture (two separate systems)**
- **Head:** 2S battery (or USB-C) → Fusion HAT+ → Raspberry Pi 5 + head servos.
- **Body:** 3S LiPo → buck converter → Servo 2040 → MG996R leg servos.

**Safety:** set and measure the buck converter's output before connecting any servo. Charge LiPos with a balance charger, in a fireproof bag, one pack at a time at 1C (2.2A) or less, never unattended. Store at ~3.8 V per cell. Unplug the LiPo whenever stepping away from the bench.

---

## 7. Soft body and fabrication materials

| Component | Qty. | Cost | Status | Purpose |
| --- | ---: | ---: | --- | --- |
| Turquoise shaggy faux fur, 60" wide | ½ yard | $23.90 | **Acquired** | Exterior body |
| Beige Minky fabric, 65" wide | 1 yard | $8.11 | **Acquired** | Body/interior/detail |
| Black Minky fabric, 65" wide | 1 yard | $9.99 | **Acquired** | Body/detail |
| Black faux fur, 65" wide | 1 yard | $20.98 | **Acquired** | Body/detail |
| Polyurethane upholstery foam | 1 | $15.49 | **Acquired** | Internal structure and padding |
| M2/M3/M4 screw assortment, 685 pieces | 1 | $8.09 | **Acquired** | Mechanical assembly |
| ½" spiral cable wrap, 20 ft | 1 | $6.99 | **Acquired** | Cable management |
| Loctite Super Glue Liquid, 2-pack | 1 | $2.98 | **Acquired** | Prototype assembly |

The pan-tilt servos are only strong enough to move the bare camera. A fur or foam head shell must be supported by the head structure, not the pan-tilt. Keep the skin light and leave the leg joints and vents around the Pi and buck converter open.

---

## 8. Development stages

| Stage | Description | Status |
| --- | --- | --- |
| 1 — Physical sensing | Micro-switch → Raspberry Pi | **Done** (Experiment 01) |
| 2 — Movement sensing | BNO085 → Raspberry Pi | **Done** (Experiment 02) |
| 3 — Physical response | Raspberry Pi → servos | **Head done**; body: Servo 2040 running on USB |
| 4 — Embodied prototype | Sensors, computing, movement, foam and fabric in one body | Head assembled; body build in progress. **Committed for Nov 18** |
| 5 — Networked interaction | krēCHer ↔ remote user | Tunnel on boot done; Pi ↔ GPU box over Tailscale working |
| 6 — Remote presence | A remote person experiences krēCHer as a physical body | Committed for Nov 18: remote camera view + head control |

---

## 9. Cost

**Documented hardware expenditure: $745.51**, plus ~$51 for the 12 new servos and the extension cables and horns (prices to add). Not included: the aluminum frame (price not documented). Bundled items (the Pi starter kit's accessories and everything inside the SunFounder kit) are not counted separately.
