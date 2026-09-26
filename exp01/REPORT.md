# Experiment 01: Physical Touch Sensing ("Active and Listening")

**Status:** Complete · **Date run:** 2026-09-20 (09:06–09:20) · **Stage:** 1, Physical Sensing

## Question
Can the Raspberry Pi 5 reliably notice when something physically presses on krēCHer's body, and tell a press from a release?

## Setup
| Part | Detail |
| --- | --- |
| Sensor | Cylewet 3-pin SPDT lever micro-switch |
| Wiring | COM → GPIO17 (pin 11), NO → GND (pin 9), NC left empty. See `switch_wiring.svg` |
| Pull-up | Pi's internal pull-up, so released = HIGH (1), pressed = LOW (0) |
| Computer | Raspberry Pi 5, bare (before the Fusion HAT+ was mounted) |
| Software | `touch_gpiod.py`: libgpiod on `gpiochip15`, waits for edge events, 50 ms debounce, prints a timestamped line on every press and release |
| Logging | `python3 -u touch_gpiod.py | tee <round>.log` |

gpiozero/lgpio could not open the GPIO chip on this Pi 5 kernel (6.12.109), so the script talks to libgpiod directly. The failed attempt is kept in `logs/led_test_gpiozero_failed.py`.

## Method
Four runs, each logged to its own file. Round 1 followed a set pattern; the other three repeated the test under different conditions. The exact conditions for Light, Fabric and Plate weren't written down at the time; the descriptions below are inferred from the file names and should be confirmed.

| Run | Log | Time | What was tested |
| --- | --- | --- | --- |
| Round 1 | `exp01_round1.log` | 09:06:07–09:07:25 | 10 single taps, then 10 held presses (~3 s each), then 10 rapid taps |
| Light | `exp01_light.log` | 09:12:17–09:12:45 | Light, gentle presses (inferred from the file name; confirm) |
| Fabric | `exp01_fabric.log` | 09:14:41–09:15:16 | Presses through fabric covering the lever (inferred; confirm) |
| Plate | `exp01_plate.log` | 09:18:52–09:19:44 | Presses through a plate over the lever (inferred; confirm) |

## Results
| Run | Presses | Releases | Unmatched | Presses held ≥1 s | Presses in the same second as the one before |
| --- | ---: | ---: | ---: | ---: | ---: |
| Round 1 | 30 | 30 | 0 | 11 | 7 |
| Light | 6 | 6 | 0 | 2 | 0 |
| Fabric | 23 | 23 | 0 | 4 | 6 |
| Plate | 20 | 20 | 0 | 5 | 3 |
| **Total** | **79** | **79** | **0** | | |

- **Every press was followed by exactly one release** across all four runs (79 of 79). The script never got stuck in "pressed" and never logged two presses in a row, so the 50 ms debounce was enough to hide switch bounce.
- **Round 1's pattern shows up cleanly in the log:** 10 taps about 1.5–2 s apart, then 9 holds of 3 s and one of 2 s, then 10 rapid taps logged within about 2 seconds (09:07:23–09:07:25).
- **Rapid tapping kept up.** The fastest bursts (Round 1 and Fabric) logged several press/release pairs inside one second without dropping events.
- **Light presses registered** (6 of 6). A gentle press still moves the lever far enough to switch.
- **Fabric and a plate did not block sensing.** Presses transmitted through a covering material still closed the switch, which matters because krēCHer will be covered in foam and fur.

## Limitations
- Timestamps are whole seconds, so short taps show 0 s holds and rapid taps can't be timed. Use `time.monotonic()` with milliseconds next time.
- There is no independent count of how many presses were attempted, so the logs show that recorded events are consistent, not that zero presses were missed. A future round should count presses by hand (or on video) and compare.
- The thickness and type of fabric and plate were not written down.
- One switch, one pin. Multiple switches (for example, one per foot) are untested.

## Conclusion
A lever micro-switch on a Pi 5 GPIO pin, read through libgpiod with a 50 ms debounce, reliably detects press and release, including light presses, rapid tapping, and presses through fabric or a plate. Stage 1 (Physical Sensing) is done.

## Follow-ups
- Log with millisecond timestamps and a hand count of attempted presses.
- Try the kit's capacitive touch module (see project note `ref_touch_switch_module_fusion_hat.md`); it senses skin rather than force and is active-high.
- Pin note: GPIO17 is still free with the Fusion HAT+ mounted; GPIO16 and GPIO21 are not (HAT audio).

## Files
- `touch_gpiod.py`: the script used
- `switch_wiring.svg`: wiring diagram
- `logs/exp01_round1.log`, `logs/exp01_light.log`, `logs/exp01_fabric.log`, `logs/exp01_plate.log`: raw logs
