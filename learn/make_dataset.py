#!/usr/bin/env python3
"""Turn logged sessions into a labelled table krēCHer can learn from.

Cuts every labelled trial into short overlapping windows (1 s long, every 0.5 s) and
describes each window with a row of numbers ("features"): how hard and how fast the IMU is
moving, whether the touch spot / PIR are on, how far the nearest thing is and whether it's
getting closer, how much current the legs draw, and so on. One row per window, plus its label.

    python3 learn/make_dataset.py                       # all sessions in data/
    python3 learn/make_dataset.py data/2026-10-29       # one day
    python3 learn/make_dataset.py --win 2 --hop 0.5     # longer windows

Writes learn/dataset.csv. Trials marked bad (x during the trial, or a pose that failed) are
left out. Simulated sessions (--dry-run) are skipped unless you pass --include-dry.
Standard library only, so it runs on the Pi or the Mac.
"""
import argparse
import bisect
import csv
import glob
import json
import math
import os
import statistics as stats

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
TRIM_START = 0.5      # skip the first half second of a trial (people react after "GO")


def load(path):
    rows = []
    with open(path) as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass            # a half-written last line if the Pi lost power
    return rows


def trials_of(rows):
    """Label intervals: list of dicts with label, block, rep, t0, t1, bad."""
    out, open_ = [], {}
    marks = [r for r in rows if r["src"] == "mark"]
    for r in rows:
        if r["src"] != "label":
            continue
        if r["edge"] == "start":
            open_ = dict(r)
        elif r["edge"] == "end" and open_.get("label") == r["label"]:
            t0, t1 = open_["t"], r["t"]
            bad = bool(r.get("bad")) or any(t0 <= m["t"] <= t1 for m in marks)
            out.append({"label": r["label"], "block": open_.get("block", ""), "rep": open_.get("rep", 0),
                        "t0": t0, "t1": t1, "bad": bad})
            open_ = {}
    return out


class Stream:
    """Time-sorted records of one kind, with fast window slicing."""

    def __init__(self, recs):
        self.recs = recs
        self.ts = [r["t"] for r in recs]

    def window(self, a, b):
        i, j = bisect.bisect_left(self.ts, a), bisect.bisect_left(self.ts, b)
        return self.recs[i:j]

    def before(self, a):
        i = bisect.bisect_left(self.ts, a)
        return self.recs[i - 1] if i else None


def mag(v):
    return math.sqrt(sum(x * x for x in v))


def sd(xs):
    return stats.pstdev(xs) if len(xs) > 1 else 0.0


def slope(ts, ys):
    """Least-squares slope (units per second)."""
    if len(ts) < 3:
        return float("nan")
    mt, my = sum(ts) / len(ts), sum(ys) / len(ys)
    den = sum((t - mt) ** 2 for t in ts)
    return sum((t - mt) * (y - my) for t, y in zip(ts, ys)) / den if den else float("nan")


def frac_on(stream, a, b):
    """Fraction of [a, b) a digital sensor was on, from its change records."""
    prev = stream.before(a)
    state = prev["v"] if prev else 0
    t, on = a, 0.0
    for r in stream.window(a, b):
        if state:
            on += r["t"] - t
        state, t = r["v"], r["t"]
    if state:
        on += b - t
    return on / (b - a), len(stream.window(a, b))


def unwrap_range(angles):
    if not angles:
        return float("nan")
    total, lo, hi = 0.0, 0.0, 0.0
    for p, q in zip(angles, angles[1:]):
        d = (q - p + 180) % 360 - 180
        total += d
        lo, hi = min(lo, total), max(hi, total)
    return hi - lo


NAN = float("nan")


def features(S, a, b):
    f = {}
    imu = S["imu"].window(a, b)
    f["imu_n"] = len(imu)
    if imu:
        am = [mag(r["acc"]) for r in imu]
        gm = [mag(r["gyr"]) for r in imu]
        f["acc_mean"], f["acc_sd"] = sum(am) / len(am), sd(am)
        f["acc_min"], f["acc_max"] = min(am), max(am)
        f["acc_jerk"] = sum(abs(q - p) for p, q in zip(am, am[1:])) / max(1, len(am) - 1)
        for k, name in enumerate("xyz"):
            ax = [r["acc"][k] for r in imu]
            f["acc_%s_mean" % name], f["acc_%s_sd" % name] = sum(ax) / len(ax), sd(ax)
        f["gyr_mean"], f["gyr_sd"], f["gyr_max"] = sum(gm) / len(gm), sd(gm), max(gm)
        roll = [r["rpy"][0] for r in imu]
        pitch = [r["rpy"][1] for r in imu]
        f["roll_mean"], f["roll_range"] = sum(roll) / len(roll), max(roll) - min(roll)
        f["pitch_mean"], f["pitch_range"] = sum(pitch) / len(pitch), max(pitch) - min(pitch)
        f["yaw_range"] = unwrap_range([r["rpy"][2] for r in imu])
    else:
        for k in ("acc_mean", "acc_sd", "acc_min", "acc_max", "acc_jerk", "acc_x_mean", "acc_x_sd",
                  "acc_y_mean", "acc_y_sd", "acc_z_mean", "acc_z_sd", "gyr_mean", "gyr_sd", "gyr_max",
                  "roll_mean", "roll_range", "pitch_mean", "pitch_range", "yaw_range"):
            f[k] = NAN

    for name in ("touch", "pir"):
        f["%s_on" % name], f["%s_changes" % name] = frac_on(S[name], a, b)

    us = S["us"].window(a, b)
    ok = [(r["t"], r["cm"]) for r in us if r.get("cm") is not None]
    f["us_echo"] = len(ok) / len(us) if us else NAN
    if ok:
        cms = [c for _, c in ok]
        f["us_min"], f["us_mean"], f["us_sd"] = min(cms), sum(cms) / len(cms), sd(cms)
        f["us_slope"] = slope([t for t, _ in ok], cms)
    else:
        f["us_min"] = f["us_mean"] = f["us_sd"] = f["us_slope"] = NAN

    body = S["body"].window(a, b)
    if body:
        amps = [r["a"] for r in body]
        vs = [r["v"] for r in body]
        f["rail_v"] = sum(vs) / len(vs)
        f["powered"] = 1.0 if f["rail_v"] >= 5 else 0.0
        f["amp_mean"], f["amp_sd"], f["amp_max"] = sum(amps) / len(amps), sd(amps), max(amps)
        f["moving"] = sum(1 for r in body if r.get("p") == "moving") / len(body)
        f["posed"] = sum(1 for r in body if r.get("p") in ("stand", "crouch", "moving")) / len(body)
        ths = [r["th"] for r in body if r.get("th") is not None]
        f["theta"] = sum(ths) / len(ths) if ths else NAN
        for k, leg in enumerate(("FL", "ML", "RL", "FR", "MR", "RR")):
            fv = [r["fv"][k] for r in body if r.get("fv")]
            f["foot_%s_v" % leg] = sum(fv) / len(fv) if fv else NAN
        f["feet_down"] = sum(sum(r.get("feet") or []) for r in body) / len(body)
    else:
        for k in ("rail_v", "powered", "amp_mean", "amp_sd", "amp_max", "moving", "posed", "theta",
                  "foot_FL_v", "foot_ML_v", "foot_RL_v", "foot_FR_v", "foot_MR_v", "foot_RR_v", "feet_down"):
            f[k] = NAN
    return f


def session_rows(path, win, hop, include_bad=False):
    rows = load(path)
    meta = next((r for r in rows if r["src"] == "meta"), {})
    session = meta.get("session") or os.path.basename(path).replace(".jsonl", "")
    S = {}
    for name in ("imu", "touch", "pir", "us"):
        S[name] = Stream([r for r in rows if r["src"] == name])
    S["body"] = Stream([r for r in rows if r["src"] == "body" and r.get("k") == "s"])
    out, skipped = [], 0
    for tr in trials_of(rows):
        if tr["bad"] and not include_bad:
            skipped += 1
            continue
        a = tr["t0"] + min(TRIM_START, (tr["t1"] - tr["t0"]) / 4)
        while a + win <= tr["t1"] + 1e-9:
            row = {"session": session, "day": os.path.basename(os.path.dirname(path)),
                   "block": tr["block"], "rep": tr["rep"], "label": tr["label"],
                   "t_start": round(a, 3), "bad": int(tr["bad"])}
            row.update(features(S, a, a + win))
            out.append(row)
            a += hop
    return out, skipped, meta


def main():
    ap = argparse.ArgumentParser(description="Logged sessions -> windowed, labelled feature table.")
    ap.add_argument("paths", nargs="*", help="session .jsonl files or folders (default: data/)")
    ap.add_argument("--win", type=float, default=1.0, help="window length, s")
    ap.add_argument("--hop", type=float, default=0.5, help="step between windows, s")
    ap.add_argument("--out", default=os.path.join(HERE, "dataset.csv"))
    ap.add_argument("--include-dry", action="store_true", help="also use --dry-run sessions")
    ap.add_argument("--include-bad", action="store_true", help="keep trials marked bad")
    args = ap.parse_args()

    paths = args.paths or [os.path.join(REPO, "data")]
    files = []
    for p in paths:
        files += sorted(glob.glob(os.path.join(p, "**", "*.jsonl"), recursive=True)) if os.path.isdir(p) else [p]
    files = [f for f in files if args.include_dry or not f.endswith("_dry.jsonl")]
    if not files:
        raise SystemExit("No sessions found in %s" % ", ".join(paths))

    all_rows = []
    for path in files:
        rows, skipped, meta = session_rows(path, args.win, args.hop, args.include_bad)
        print("%-34s %5d windows%s" % (os.path.basename(path), len(rows),
                                         "  (%d bad trials left out)" % skipped if skipped else ""))
        all_rows += rows
    if not all_rows:
        raise SystemExit("No labelled windows. Were these free-mode sessions with no labels typed?")

    cols = list(all_rows[0].keys())
    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in all_rows:
            w.writerow({k: ("" if isinstance(v, float) and math.isnan(v) else
                            round(v, 4) if isinstance(v, float) else v) for k, v in r.items()})

    tally = {}
    for r in all_rows:
        tally[r["label"]] = tally.get(r["label"], 0) + 1
    print("\n%d windows from %d sessions -> %s" % (len(all_rows), len(files), os.path.relpath(args.out)))
    for label, n in sorted(tally.items(), key=lambda kv: -kv[1]):
        print("  %-14s %5d" % (label, n))


if __name__ == "__main__":
    main()
