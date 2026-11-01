# mag_probe.py: find the spot on krēCHer where the servos disturb the BNO085's compass least.
# Shows the magnetic field strength (uT) and the compass heading, twice a second.
# Earth's field is ~25-65 uT. A good spot changes by less than ~2 uT and ~3 deg
# between servos OFF and servos ON (holding neutral).
#
#   source ~/venvs/imu/bin/activate
#   python3 ~/krecher/sensors/mag_probe.py
#
# Body on the box the WHOLE time (don't move it between readings).
# For each spot: hold or tape the board there, flat, arrow the same way,
#   1) servos off: press Enter -> it records 3 s
#   2) start hold_2min.py in the other window, wait for neutral: press Enter -> records 3 s
#   3) stop hold_2min (Ctrl+C there) before moving the board to the next spot.
import math
import time

import board
from adafruit_bno08x import BNO_REPORT_MAGNETOMETER, BNO_REPORT_ROTATION_VECTOR
from adafruit_bno08x.i2c import BNO08X_I2C


def heading(i, j, k, real):
    return math.degrees(math.atan2(2 * (real * k + i * j), 1 - 2 * (j * j + k * k)))


def sample(bno, secs=3.0):
    mags, ys, yc = [], 0.0, 0.0
    end = time.monotonic() + secs
    while time.monotonic() < end:
        mx, my, mz = bno.magnetic
        mags.append(math.sqrt(mx * mx + my * my + mz * mz))
        y = math.radians(heading(*bno.quaternion))
        ys += math.sin(y); yc += math.cos(y)
        time.sleep(0.05)
    return sum(mags) / len(mags), math.degrees(math.atan2(ys, yc))


bno = BNO08X_I2C(board.I2C())
bno.enable_feature(BNO_REPORT_MAGNETOMETER)
bno.enable_feature(BNO_REPORT_ROTATION_VECTOR)
time.sleep(0.5)

print("Magnetometer probe. Body on the box; don't move it between readings.")
results = []
while True:
    spot = input("\nName this spot (e.g. 'now', 'front edge', 'raised 2in'), or just Enter to finish: ").strip()
    if not spot:
        break
    input("  Board in place, SERVOS OFF, hands away. Press Enter... ")
    b0, h0 = sample(bno)
    print("    off: %.1f uT, heading %.1f" % (b0, h0))
    input("  Now start hold_2min.py in the other window. When it's holding neutral, hands away, press Enter... ")
    b1, h1 = sample(bno)
    dh = (h1 - h0 + 180) % 360 - 180
    print("    on:  %.1f uT, heading %.1f   ->  change %+.1f uT, %+.1f deg" % (b1, h1, b1 - b0, dh))
    results.append((spot, b0, b1 - b0, dh))
    print("  Stop hold_2min (Ctrl+C in its window) before moving the board.")

print("\n===== paste this to Claude =====")
for spot, b0, db, dh in results:
    verdict = "GOOD" if abs(db) < 2 and abs(dh) < 3 else ("ok" if abs(db) < 5 and abs(dh) < 6 else "bad")
    print("%-14s field %.1f uT | servos on: %+.1f uT, %+.1f deg | %s" % (spot, b0, db, dh, verdict))
print("================================")
