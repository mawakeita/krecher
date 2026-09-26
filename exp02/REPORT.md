# Experiment 02: Movement and Orientation Sensing

**Status:** In progress (sensor reading works; logged trials and the head reaction are next) · **Date started:** 2026-09-26 · **Stage:** 2, Movement Sensing

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

## Limitations
- The first run's output was not saved to a file (it was only printed). Logged trials come next.
- Roll and pitch were not checked against a known angle (for example, a protractor or a 45° wedge).
- The yaw heading depends on the magnetometer, which the Fusion HAT+ and nearby servos may disturb. Untested.
- The sensor was loose on its cable, not mounted to the head or body.

## Next steps
- **Sprint 5, logging:** save timestamped roll / pitch / yaw to `exp02/logs/` during set movements (still, tilt, rotate, shake), in the style of Exp. 01.
- **Sprint 6, reaction:** map IMU pitch to the head's tilt servo and yaw to pan, clamped to ±20° / ±30° and smoothed, so the camera head follows the sensor. This is krēCHer's first sense → react loop.
- Later: mount the IMU in the body, check the angles against known references, test near the servos.

## Files
- `imu_read.py`: the script used
- `logs/`: (to come in Sprint 5)
