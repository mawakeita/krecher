# Exp. 02: read orientation from the BNO085 (I2C 0x4A via the Fusion HAT+ I2C port).
# Run inside the venv:  source ~/venvs/imu/bin/activate && python3 exp02/imu_read.py
import math
import time

import board
from adafruit_bno08x import BNO_REPORT_ROTATION_VECTOR
from adafruit_bno08x.i2c import BNO08X_I2C


def to_euler(i, j, k, real):
    """Quaternion -> roll, pitch, yaw in degrees."""
    roll = math.atan2(2 * (real * i + j * k), 1 - 2 * (i * i + j * j))
    s = max(-1.0, min(1.0, 2 * (real * j - k * i)))
    pitch = math.asin(s)
    yaw = math.atan2(2 * (real * k + i * j), 1 - 2 * (j * j + k * k))
    return tuple(math.degrees(a) for a in (roll, pitch, yaw))


i2c = board.I2C()
bno = BNO08X_I2C(i2c)
bno.enable_feature(BNO_REPORT_ROTATION_VECTOR)
print("BNO085 ready. Tilt and turn the board. Ctrl+C to stop.")

try:
    while True:
        i, j, k, real = bno.quaternion
        roll, pitch, yaw = to_euler(i, j, k, real)
        print(f"roll {roll:7.1f}   pitch {pitch:7.1f}   yaw {yaw:7.1f}")
        time.sleep(0.1)
except KeyboardInterrupt:
    print("\nStopped.")
