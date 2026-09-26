# Exp. 02, Sprint 5: guided, logged BNO085 trial.
# Walks you through set movements and saves every reading to exp02/logs/ as CSV,
# plus a short per-phase summary.
# Run inside the venv:  source ~/venvs/imu/bin/activate && python3 exp02/imu_log.py
import csv
import math
import os
import statistics
import time
from datetime import datetime

import board
from adafruit_bno08x import BNO_REPORT_ACCELEROMETER, BNO_REPORT_ROTATION_VECTOR
from adafruit_bno08x.i2c import BNO08X_I2C

RATE_HZ = 20
PHASES = [
    # (name, seconds, instruction)
    ("still", 10, "Lay the sensor flat and don't touch it."),
    ("roll", 15, "Tilt it slowly LEFT and RIGHT, a few times."),
    ("pitch", 15, "Tilt it slowly FORWARD and BACK, a few times."),
    ("yaw", 15, "Keep it flat and TURN it around, like a compass."),
    ("shake", 10, "SHAKE it (gently, hold the cable)."),
    ("still_end", 10, "Lay it flat again and let go."),
]


def to_euler(i, j, k, real):
    """Quaternion -> roll, pitch, yaw in degrees."""
    roll = math.atan2(2 * (real * i + j * k), 1 - 2 * (i * i + j * j))
    s = max(-1.0, min(1.0, 2 * (real * j - k * i)))
    pitch = math.asin(s)
    yaw = math.atan2(2 * (real * k + i * j), 1 - 2 * (j * j + k * k))
    return tuple(math.degrees(a) for a in (roll, pitch, yaw))


def summarize(rows):
    lines = []
    for name, _, _ in PHASES:
        r = [row for row in rows if row["phase"] == name]
        if not r:
            continue
        line = f"{name:<10} n={len(r):4d}"
        for axis in ("roll", "pitch", "yaw"):
            v = [row[axis] for row in r]
            line += f"  {axis} {min(v):7.1f}..{max(v):7.1f} (sd {statistics.pstdev(v):5.1f})"
        a = [row["accel"] for row in r]
        line += f"  accel max {max(a):5.1f} m/s2"
        lines.append(line)
    return lines


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    logdir = os.path.join(here, "logs")
    os.makedirs(logdir, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    csv_path = os.path.join(logdir, f"exp02_{stamp}.csv")
    summary_path = os.path.join(logdir, f"exp02_{stamp}_summary.txt")

    bno = BNO08X_I2C(board.I2C())
    bno.enable_feature(BNO_REPORT_ROTATION_VECTOR)
    bno.enable_feature(BNO_REPORT_ACCELEROMETER)

    print("krēCHer Experiment 02: logged movement trial")
    print(f"Saving to {csv_path}")
    print(f"{len(PHASES)} phases, about {sum(p[1] for p in PHASES)} s total. Ctrl+C stops early (data is kept).\n")

    rows, errors = [], 0
    t0 = time.monotonic()
    period = 1.0 / RATE_HZ
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["t_ms", "clock", "phase", "roll", "pitch", "yaw", "accel"])
        w.writeheader()
        try:
            for name, seconds, instruction in PHASES:
                print(f"--- {name.upper()} ({seconds} s): {instruction}")
                for n in (3, 2, 1):
                    print(f"    starting in {n}...", end="\r", flush=True)
                    time.sleep(1)
                print("    GO                 ")
                end = time.monotonic() + seconds
                next_t = time.monotonic()
                while time.monotonic() < end:
                    try:
                        roll, pitch, yaw = to_euler(*bno.quaternion)
                        ax, ay, az = bno.acceleration
                    except Exception as e:  # keep going if one read fails
                        errors += 1
                        print(f"    read error {errors}: {e}")
                        continue
                    row = {
                        "t_ms": round((time.monotonic() - t0) * 1000),
                        "clock": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                        "phase": name,
                        "roll": round(roll, 2),
                        "pitch": round(pitch, 2),
                        "yaw": round(yaw, 2),
                        "accel": round(math.sqrt(ax * ax + ay * ay + az * az), 2),
                    }
                    w.writerow(row)
                    rows.append(row)
                    if len(rows) % RATE_HZ == 0:  # show one line per second
                        print(f"    roll {roll:7.1f}  pitch {pitch:7.1f}  yaw {yaw:7.1f}  accel {row['accel']:5.1f}")
                    next_t += period
                    time.sleep(max(0.0, next_t - time.monotonic()))
        except KeyboardInterrupt:
            print("\nStopped early.")

    summary = summarize(rows)
    header = [
        f"Exp. 02 logged trial {stamp}",
        f"readings: {len(rows)}   read errors: {errors}   rate target: {RATE_HZ} Hz",
        "",
    ]
    with open(summary_path, "w") as f:
        f.write("\n".join(header + summary) + "\n")
    print("\n" + "\n".join(header + summary))
    print(f"\nSaved {csv_path}\nSaved {summary_path}")


if __name__ == "__main__":
    main()
