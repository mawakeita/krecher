# KrēCHer BOM Update: Moving Head, Expression and Extra Sensing

Date: 2026-09-22 (updated 2026-09-24: kit camera cable confirmed to fit the Pi 5, extra cable being returned; HAT/Servo 2040 connection corrected). Status: proposed. Camera, mic/speaker, GPIO pin usage, servo model, case fit, and head architecture confirmed.

## Decision

Add the SunFounder AI Fusion Lab Kit (kit only, no NVMe Raft) to support a moving head on top of the hexapod body. Do not buy the fanxiang 256GB NVMe SSD or the Dual NVMe Raft. The 128GB microSD is sufficient, and the Raft would compete with the cooling case and the HAT stack for the Pi 5's connectors.

## Head architecture (decided 2026-09-22)

The Pi 5 + Fusion HAT+ stack will run bare, without the Seeed case tray, screwed directly onto a stand using the kit's own M2.5×8 / M2.5×20+6 standoffs (already in the kit's parts bag — no new hardware needed). This stand-mounted Pi+HAT assembly IS the head structure itself (its "skull"), not something the pan-tilt has to move.

The pan-tilt mechanism sits on/in this head and only swivels the camera board (a few grams), not the Pi+HAT assembly. This resolves the earlier torque concern: the SF006PRO's ~5 kgf·cm rating is easily sufficient for just the camera, since it never has to lift the head's own electronics.

Open question: whether the head as a whole (the stand) will also turn/nod relative to the hexapod body (a "neck" joint), which would need its own, larger servo, separate from the two small pan-tilt servos already dedicated to camera movement. Not yet decided.

Case: the Seeed Studio case tray is being left off entirely (not just the fan lid) to save weight, since the Pi+HAT will be permanently mounted into the head stand rather than sitting in the desk case. This is a one-time change — the board is only clipped into the tray, nothing soldered or glued.

## New items

| Component | Qty | Cost | Status | Stage | Purpose |
|---|---|---|---|---|---|
| SunFounder AI Fusion Lab Kit (kit only) | 1 | $98.99 (SunFounder list price; confirm the Amazon price) | Acquired | 3-6 | Head, camera, voice, face, extra sensing |
| Fusion HAT+ (in kit) | 1 | In kit | Acquired, test-fit confirmed on bare Pi 5 board | 3-6 | Runs head servos; built-in speaker and microphone; 4-channel DC motor driver via onboard MCU |
| Pan-tilt mount + 2 SF006PRO servos (in kit) | 1 | In kit | Acquired | 4-6 | Two-axis camera movement within the fixed head |
| Camera: 5MP OV5647, FFC/CSI (in kit) | 1 | In kit | Acquired, working (first test photo taken 2026-09-24) | 4-6 | Vision and tracking (YOLO, OpenCV, MediaPipe) |
| Pi 5 CSI camera cable (separately bought) | 1 | ~$1-5 est. | To return. Not needed: the kit's included camera cable fits the Pi 5. The earlier "wrong width" note came from checking the wrong port on the Pi | — | — |
| OLED screen, WS2812 RGB, ultrasonic, PIR, touch, joystick (in kit) | 1 each | In kit | Acquired | 4-6 | Face, mood light, sensing, input |
| PinPal pin-label board (in kit) | 1 | In kit | Acquired | all | Pin identification on the HAT's header |
| M2.5×8 / M2.5×20+6 standoffs (in kit) | multiple | In kit | Acquired | 4-6 | Mount the bare Pi+HAT stack onto the head stand |

## Servo specs — SunFounder SF006PRO (confirmed from official docs)

- Stall torque: ≥5 kgf·cm
- Voltage: DC 4-6V (rated 5V)
- Weight: 13.5g
- Gears: plastic + metal hybrid
- Angle: 90°±10° normal travel, 180°±10° max, 360° mechanical limit

With the head architecture above (pan-tilt moves only the camera, not the Pi+HAT), this torque rating is sufficient. It would NOT be sufficient to move a full furred/foam head shell — keep that possibility in mind only if a design change later asks the pan-tilt to carry more than the bare camera.

## GPIO pin usage — from SunFounder's official Fusion HAT+ / PinPal docs

**Truly reserved (never use for anything else):**
- GPIO0 / GPIO1 (ID_SD / ID_SC): onboard EEPROM.
- GPIO18 / 19 / 20 / 21: I2S audio (speaker + mic).
- GPIO2 / GPIO3 (I2C): carries commands to the HAT's onboard motor-control microcontroller (the "P4-P11" silkscreen labels are that microcontroller's own internal channel names, not Pi GPIOs — the 4 DC motor drivers don't use header pins directly).

**Duplicated, not consumed (free to use through ONE access point only — Pi's main header or HAT's breakout, not both):**
- GPIO4, 17, 22, 27 (general GPIO)
- GPIO14, 15 (UART — use the Pi's main header since the Servo 2040 connects by USB)
- GPIO6, 8, 9, 10, 11 (SPI — GPIO10/MOSI also feeds the onboard WS2812 connector if it's plugged in)

**Free and unaffected:** GPIO5, 7, 12, 13, 16, 23, 24, 25, 26.

**Practical takeaway:** the Stage 1 micro-switch can go on GPIO5 or GPIO16, or nearly any pin outside the reserved set.

## I2C bus sharing (BNO085)

The BNO085 connects over I2C (GPIO2/3), the same bus the HAT uses to talk to its onboard motor microcontroller. Multiple I2C devices coexist fine by address. Do not also connect the kit's own 10-axis IMU on the same bus without checking for an address conflict; since it duplicates the BNO085, leave it unconnected.

## Power warning

The Fusion HAT+ battery input is confirmed 6.0V to 8.4V (2S Li-ion) via a 3-pin XH2.54 connector — confirmed from docs and the spec label on the board. The 3S LiPo (11.1V nominal, 12.6V full) must NEVER be connected to the HAT. Power the HAT from its own pack or USB-C; use the 3S battery only for the hexapod servos through the buck converter / Servo 2040 path.

## Still to confirm before assembling further

1. Whether the head as a whole needs a separate neck/turn joint beyond the pan-tilt's camera movement (open design question above).
2. The kit-only Amazon price.
3. Standoff/mounting design for attaching the head stand to the hexapod body.

## Overlaps (already owned)

- 10-axis IMU duplicates the Adafruit BNO085 (leave unconnected).
- 2 micro-switches duplicate the 25 Cylewet switches.
- The relay duplicates the 3 Ferwooh relay modules.
- Servo control: the Servo 2040's 18 channels are reserved for the hexapod legs, so the head is driven separately by the Fusion HAT+, which stacks directly on the Pi's GPIO header. The Servo 2040 is the board that connects to the Pi by USB.

## Removed from cart

- fanxiang S500 Pro 256GB NVMe SSD ($56.99): returned/cancelled.
- SunFounder Kit + Dual NVMe Raft bundle ($122.48): replaced with the kit only.

## Cost impact

Documented expenditure: $530.86 + $98.99 = $629.85, assuming the kit is bought at the SunFounder list price. The separately bought camera cable (~$1-5) is being returned, so it doesn't add to the total.
