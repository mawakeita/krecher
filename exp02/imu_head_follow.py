# Exp. 02, Sprint 6: first sense -> react loop.
# The camera head follows the BNO085: tilt the sensor forward/back and the camera
# tilts; turn it left/right and the camera pans. Whatever way the sensor points
# when the script starts counts as "straight ahead".
#
# Run inside the venv (it can also see the system's fusion_hat library):
#   source ~/venvs/imu/bin/activate && python3 exp02/imu_head_follow.py
import math
import time

import board
from adafruit_bno08x import BNO_REPORT_ROTATION_VECTOR
from adafruit_bno08x.i2c import BNO08X_I2C
from fusion_hat.servo import Servo

# --- settings you may want to change -------------------------------------
PAN_CH, TILT_CH = 2, 3      # Fusion HAT+ PWM channels (as in head/center_servos.py)
PAN_LIMIT = 30              # degrees; tested safe range is +/-30
TILT_LIMIT = 20             # degrees; tested safe range is +/-20
PAN_SIGN = 1                # set to -1 if the camera pans the wrong way
TILT_SIGN = 1               # set to -1 if the camera tilts the wrong way
SMOOTHING = 0.25            # 0..1; lower = smoother but slower to follow
DEADBAND = 0.5              # degrees; ignore tinier changes (less servo buzz)
RATE_HZ = 20
# ---------------------------------------------------------------------------


def to_euler(i, j, k, real):
    roll = math.atan2(2 * (real * i + j * k), 1 - 2 * (i * i + j * j))
    s = max(-1.0, min(1.0, 2 * (real * j - k * i)))
    pitch = math.asin(s)
    yaw = math.atan2(2 * (real * k + i * j), 1 - 2 * (j * j + k * k))
    return tuple(math.degrees(a) for a in (roll, pitch, yaw))


def wrap180(a):
    """Keep an angle between -180 and 180 so crossing +/-180 doesn't jump."""
    return (a + 180.0) % 360.0 - 180.0


def clamp(v, limit):
    return max(-limit, min(limit, v))


def main():
    bno = BNO08X_I2C(board.I2C())
    bno.enable_feature(BNO_REPORT_ROTATION_VECTOR)
    pan, tilt = Servo(PAN_CH), Servo(TILT_CH)
    pan.angle(0)
    tilt.angle(0)

    print("krēCHer: head follows the IMU")
    print("Hold the sensor pointing 'straight ahead' and keep it still...")
    time.sleep(1.0)
    samples = []
    for _ in range(20):
        _, p, y = to_euler(*bno.quaternion)
        samples.append((p, y))
        time.sleep(0.05)
    pitch0 = sum(p for p, _ in samples) / len(samples)
    # average yaw via sin/cos so readings near +/-180 average correctly
    yaw0 = math.degrees(math.atan2(sum(math.sin(math.radians(y)) for _, y in samples),
                                   sum(math.cos(math.radians(y)) for _, y in samples)))
    print(f"Home set: pitch {pitch0:.1f}, yaw {yaw0:.1f}. Now tilt and turn it. Ctrl+C to stop.\n")

    cur_pan = cur_tilt = 0.0
    sent_pan = sent_tilt = 0.0
    period = 1.0 / RATE_HZ
    n = 0
    try:
        while True:
            try:
                _, pitch, yaw = to_euler(*bno.quaternion)
            except Exception as e:
                print("read error:", e)
                time.sleep(period)
                continue
            target_tilt = clamp(TILT_SIGN * (pitch - pitch0), TILT_LIMIT)
            target_pan = clamp(PAN_SIGN * wrap180(yaw - yaw0), PAN_LIMIT)

            cur_tilt += SMOOTHING * (target_tilt - cur_tilt)
            cur_pan += SMOOTHING * (target_pan - cur_pan)

            if abs(cur_tilt - sent_tilt) >= DEADBAND:
                tilt.angle(round(cur_tilt, 1))
                sent_tilt = cur_tilt
            if abs(cur_pan - sent_pan) >= DEADBAND:
                pan.angle(round(cur_pan, 1))
                sent_pan = cur_pan

            n += 1
            if n % RATE_HZ == 0:
                print(f"sensor pitch {pitch - pitch0:6.1f} yaw {wrap180(yaw - yaw0):6.1f}"
                      f"  ->  head tilt {sent_tilt:5.1f} pan {sent_pan:5.1f}")
            time.sleep(period)
    except KeyboardInterrupt:
        print("\nStopping, returning head to center.")
    finally:
        pan.angle(0)
        tilt.angle(0)
        time.sleep(0.5)


if __name__ == "__main__":
    main()
