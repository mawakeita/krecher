# imu_axes.py: guided axis test for the BNO085 on krēCHer's body.
# It asks for one move at a time, measures roll / pitch / yaw before and after,
# and prints which number each move changed and in which direction.
# Paste the summary at the end to Claude.
#
#   source ~/venvs/imu/bin/activate
#   python3 ~/krecher/sensors/imu_axes.py
#
# No LiPo needed. krēCHer sits flat on the table, front pointing away from you.
import math
import time

import board
from adafruit_bno08x import BNO_REPORT_ROTATION_VECTOR
from adafruit_bno08x.i2c import BNO08X_I2C

MOVES = [
    ("nose_down",  "Tip the NOSE DOWN about 20 deg (front lower than back)"),
    ("right_down", "Tip the RIGHT SIDE DOWN about 20 deg (krēCHer's right, seen from behind)"),
    ("turn_left",  "TURN LEFT on the spot about 45 deg (counter-clockwise, seen from above)"),
]
NAMES = ("roll", "pitch", "yaw")


def to_euler(i, j, k, real):
    roll = math.atan2(2 * (real * i + j * k), 1 - 2 * (i * i + j * j))
    s = max(-1.0, min(1.0, 2 * (real * j - k * i)))
    pitch = math.asin(s)
    yaw = math.atan2(2 * (real * k + i * j), 1 - 2 * (j * j + k * k))
    return [math.degrees(a) for a in (roll, pitch, yaw)]


def wrap(d):
    return (d + 180) % 360 - 180


def average(bno, secs=1.5):
    """Average roll/pitch/yaw over secs (yaw averaged as an angle)."""
    rs, ps, ys, yc = [], [], 0.0, 0.0
    end = time.monotonic() + secs
    while time.monotonic() < end:
        r, p, y = to_euler(*bno.quaternion)
        rs.append(r); ps.append(p)
        ys += math.sin(math.radians(y)); yc += math.cos(math.radians(y))
        time.sleep(0.02)
    return [sum(rs) / len(rs), sum(ps) / len(ps), math.degrees(math.atan2(ys, yc))]


i2c = board.I2C()
bno = BNO08X_I2C(i2c)
bno.enable_feature(BNO_REPORT_ROTATION_VECTOR)
time.sleep(0.5)

print("IMU axis test: 3 moves. Between moves, put krēCHer back flat in the same spot.\n")
results = []
first_rest = None
for key, text in MOVES:
    input("Set krēCHer FLAT and still, then press Enter... ")
    rest = average(bno)
    if first_rest is None:
        first_rest = rest
    print("   rest:   roll %6.1f   pitch %6.1f   yaw %6.1f" % tuple(rest))
    input(">> " + text + ", HOLD it there, then press Enter... ")
    moved = average(bno)
    d = [moved[0] - rest[0], moved[1] - rest[1], wrap(moved[2] - rest[2])]
    big = max(range(3), key=lambda n: abs(d[n]))
    results.append((key, d, big))
    print("   change: roll %+6.1f   pitch %+6.1f   yaw %+6.1f  ->  %s %s\n"
          % (d[0], d[1], d[2], NAMES[big], "UP" if d[big] > 0 else "DOWN"))

input("Last one: set krēCHer FLAT in the same spot as at the start, then press Enter... ")
end_rest = average(bno)
drift = [end_rest[0] - first_rest[0], end_rest[1] - first_rest[1]]

print("\n===== paste this to Claude =====")
for key, d, big in results:
    print("%-10s -> %-5s %-4s  (roll %+.1f, pitch %+.1f, yaw %+.1f)"
          % (key, NAMES[big], "UP" if d[big] > 0 else "DOWN", d[0], d[1], d[2]))
print("rest start: roll %.1f pitch %.1f | rest end: roll %.1f pitch %.1f | drift roll %+.1f pitch %+.1f"
      % (first_rest[0], first_rest[1], end_rest[0], end_rest[1], drift[0], drift[1]))
if max(abs(drift[0]), abs(drift[1])) > 1.5:
    print("WARNING: flat readings moved > 1.5 deg: the board may be loose, or krēCHer sat differently.")
print("================================")
