# Experiment 02: Movement and Orientation Sensing

**Status:** In progress (sensing done and logged; the head reaction is next) · **Date started:** 2026-09-26 · **Stage:** 2, Movement Sensing

## Question
Can krēCHer sense how it is tilted and turned, clearly enough to react to its own movement?

## Setup
| Part | Detail |
| --- | --- |
| Sensor | Adafruit BNO085 9-DoF IMU (product 4754): accelerometer, gyroscope and magnetometer with on-chip sensor fusion |
| Connection | 4-wire cable from the SunFounder kit, Fusion HAT+ I2C port (GND · 3V3 · SDA · SCL) → BNO085 STEMMA QT port. No soldering |
| Bus | I2C bus 1 (GPIO2/3), shared with the Fusion HAT+ (address `17`). BNO085 at `4a`. No conflict |
| Computer | Raspberry Pi 5 with Fusion HAT+ mounted, in the head |
| Software | Python venv `~/venvs/imu` with `adafruit-circuitpython-bno08x` 1.3.3 and `adafruit-blinka` 9.2.0 |
| Script | `imu_read.py`: enables the rotation-vector report, converts the quaternion to roll / pitch / yaw in degrees, prints 10 times a second |

Run it with:
```
source ~/venvs/imu/bin/activate
python3 exp02/imu_read.py
```

## Method so far (first reading, 2026-09-26)
1. Took an I2C baseline with `i2cdetect -y 1` before connecting: only `17` (the HAT, shown as `UU` because its driver owns it).
2. Powered off, connected the BNO085, powered on: `4a` appeared.
3. Ran `imu_read.py` for about 40 seconds (~400 readings): left still, tilted side to side, tilted forward and back, turned it flat, then moved it freely and set it down.

## Results so far
| Check | Result |
| --- | --- |
| Detected on I2C | Yes, at `4a` |
| Errors or freezes | None in ~400 readings, at the Pi's default I2C speed. The known BNO08x clock-stretching problem on Raspberry Pi did not appear |
| Still, at start | roll −3.2°, pitch −8.1 to −8.0°, yaw 68.3° for about 5 s (changes ≤ 0.1°) |
| Roll (side tilt) | Followed the movement, about −44° to +73° in deliberate tilts |
| Pitch (forward/back tilt) | Followed the movement, about −38° to +77° |
| Yaw (turning flat) | Followed the movement and wrapped from +176.6° to −163.6° as expected (range is −180° to +180°) |
| Still, after being set down | Settled to roll ≈ −14.4°, pitch ≈ −15.2° → −14.6°, yaw ≈ 21.5°; slow drift of about 0.6° over ~7 s |

**So far:** the BNO085 works through the HAT's I2C port with no extra configuration, and all three axes respond smoothly and in the expected direction.

## Logged trial (Sprint 5, 2026-09-26 15:23)
Script `imu_log.py` guided six timed phases, sampling at 20 Hz with millisecond timestamps, and saved every reading plus a per-phase summary.

- Data: `logs/exp02_2026-09-26_1523.csv` (1,500 readings) and `logs/exp02_2026-09-26_1523_summary.txt`
- **Read errors: 0.** The loop held exactly 20 readings a second (200 per 10 s phase, 300 per 15 s phase).

| Phase | What I did | Roll range (sd) | Pitch range (sd) | Yaw range (sd) | Accel max |
| --- | --- | --- | --- | --- | --- |
| still | Flat, untouched, 10 s | 5.6 to 8.1° (0.2) | −2.5 to 0.0° (0.2) | 81.7° (0.0) | 9.6 m/s² |
| roll | Tilt left/right, 15 s | **−73.2 to 62.5° (38.5)** | 3.1 to 20.8° (2.7) | 35.5 to 61.5° (5.0) | 13.1 m/s² |
| pitch | Tilt forward/back, 15 s | −25.0 to 7.3° (5.5) | **−25.7 to 30.9° (17.7)** | 47.2 to 57.2° (1.6) | 21.1 m/s² |
| yaw | Flat, turned around, 15 s | −19.0 to 13.7° (7.8) | −19.0 to 10.5° (5.8) | **−179.9 to 177.8° (93.6)** | 11.5 m/s² |
| shake | Shaken by hand, 10 s | −19.8 to 49.9° (11.4) | −23.7 to 26.6° (9.0) | 7.7 to 60.8° (9.8) | **40.5 m/s²** |
| still_end | Set down, let go, 10 s | 7.2 to 39.0° (6.4) | −4.1 to 6.6° (1.4) | 49.5 to 66.4° (1.5) | 12.9 m/s² |

What the numbers show:
- **Each movement shows up on the right axis.** In each tilt phase the intended axis has by far the largest spread (roll sd 38.5, pitch sd 17.7, yaw covering the full circle), while the other two stay comparatively small. The sensor separates the three kinds of movement cleanly.
- **Still is really still.** At rest the spread is 0.2° or less on roll and pitch, and 0.0° on yaw.
- **Shaking is easy to detect.** Total acceleration sits at about 9.6 m/s² at rest (gravity; slightly under 9.81, a small offset) and peaks at 40.5 m/s² (about 4 g) while shaking. A threshold around 15 m/s² would separate shaking from normal tilting in this trial (tilting peaked at 21.1 m/s² once, so a short time window or a higher threshold is safer).
- **Yaw wraps around.** Turning past ±180° jumps from +177.8° to −179.9°, which inflates yaw's sd. Anything that follows yaw (like the head's pan) must handle the wrap.
- **still_end includes the setting-down moment.** Its larger ranges come from the first second or two; the live output shows it settling at roll 7.4°, pitch 2.4°, yaw 59.8°. Yaw differs from the first still phase (81.7°) because the sensor was set down facing a different way, not from drift.

## Limitations
- The first reading session (morning) was only printed, not saved; the logged trial above is the reference data.
- One logged trial so far; movements were done by hand, so speeds and angles vary.
- Roll and pitch were not checked against a known angle (for example, a protractor or a 45° wedge).
- The yaw heading depends on the magnetometer, which the Fusion HAT+ and nearby servos may disturb. Untested.
- The sensor was loose on its cable, not mounted to the head or body.

## Next steps
- Sprint 5, logging: **done** (see above).
- **Sprint 6, reaction:** map IMU pitch to the head's tilt servo and yaw to pan, clamped to ±20° / ±30° and smoothed, so the camera head follows the sensor. This is krēCHer's first sense → react loop.
- Later: mount the IMU in the body, check the angles against known references, test near the servos.

## Files
- `imu_read.py`: the script used
- `imu_log.py`: guided logging script (Sprint 5)
- `logs/exp02_2026-09-26_1523.csv`, `logs/exp02_2026-09-26_1523_summary.txt`: first logged trial
