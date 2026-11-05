#!/usr/bin/env python3
"""Teach krēCHer to recognise what's happening to it, and check how well it learned.

Reads learn/dataset.csv (from make_dataset.py), trains a random forest (many small
decision trees voting), and tests it honestly: it never tests on a session it trained on.
With one session only, it holds out one repetition at a time instead.

    pip install scikit-learn joblib          # once, on the Mac or the Pi
    python3 learn/train.py
    python3 learn/train.py --grouped          # merge labels into the study's events
    python3 learn/train.py --drop pet,bump    # leave labels out

Prints accuracy, which labels get confused with which, the most useful features, and how
long one prediction takes on this machine (for the on-device vs server comparison).
Saves the model trained on everything to learn/models/.
"""
import argparse
import csv
import os
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
META = ("session", "day", "block", "rep", "label", "t_start", "bad")

# The independent study's events, as groups of protocol labels (used with --grouped).
GROUPS = {
    "resting": ["rest_limp", "rest_floor", "stand_still", "crouch_still"],
    "moving_itself": ["stand_up", "sit_down"],
    "touched": ["touch_tap", "touch_hold", "pet"],
    "approached": ["approach"],
    "passed_by": ["pass_by"],
    "bumped": ["bump"],
    "picked_up": ["pick_up"],
    "held": ["held_still"],
    "carried": ["carry"],
    "rotated": ["rotate"],
    "shaken": ["shake"],
    "put_down": ["put_down"],
}


def load(path, grouped, drop):
    to_group = {lab: g for g, labs in GROUPS.items() for lab in labs}
    rows = []
    with open(path) as f:
        for r in csv.DictReader(f):
            if r["label"] in drop:
                continue
            if grouped:
                r["label"] = to_group.get(r["label"], r["label"])
            rows.append(r)
    feats = [c for c in rows[0] if c not in META]
    X = [[float(r[c]) if r[c] not in ("", "nan") else -1.0 for c in feats] for r in rows]
    y = [r["label"] for r in rows]
    return rows, feats, X, y


def main():
    ap = argparse.ArgumentParser(description="Train and test krēCHer's event classifier.")
    ap.add_argument("--data", default=os.path.join(HERE, "dataset.csv"))
    ap.add_argument("--grouped", action="store_true", help="merge labels into study events")
    ap.add_argument("--drop", default="", help="comma-separated labels to leave out")
    ap.add_argument("--trees", type=int, default=150)
    args = ap.parse_args()

    try:
        import joblib
        import numpy as np
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix
    except ImportError:
        raise SystemExit("Needs scikit-learn:  pip install scikit-learn joblib")

    drop = {d.strip() for d in args.drop.split(",") if d.strip()}
    rows, feats, X, y = load(args.data, args.grouped, drop)
    X, y = np.array(X), np.array(y)
    labels = sorted(set(y))

    sessions = sorted({r["session"] for r in rows})
    if len(sessions) >= 2:
        groups = np.array([r["session"] for r in rows])
        how = "leave one session out (%d sessions)" % len(sessions)
    else:
        groups = np.array(["%s/%s/%s" % (r["session"], r["block"], r["rep"]) for r in rows])
        how = "one session only: leave one repetition out"
    folds = sorted(set(groups))
    if len(folds) < 2:
        raise SystemExit("Need at least 2 sessions or 2 reps to test honestly. Log more first.")

    print("%d windows · %d labels · %d features · %s\n" % (len(y), len(labels), len(feats), how))
    pred = np.empty_like(y)
    for g in folds:
        test = groups == g
        clf = RandomForestClassifier(n_estimators=args.trees, min_samples_leaf=2,
                                     class_weight="balanced", random_state=0, n_jobs=-1)
        clf.fit(X[~test], y[~test])
        pred[test] = clf.predict(X[test])

    acc = accuracy_score(y, pred)
    bal = balanced_accuracy_score(y, pred)
    print("Accuracy on unseen data: %.0f%%   (balanced across labels: %.0f%%, chance ~%.0f%%)\n"
          % (100 * acc, 100 * bal, 100 / len(labels)))

    cm = confusion_matrix(y, pred, labels=labels)
    w = max(len(lab) for lab in labels)
    print("Per label: how often it was recognised, and what it was mistaken for most")
    for i, lab in enumerate(labels):
        n = cm[i].sum()
        right = cm[i, i]
        wrong = [(cm[i, j], labels[j]) for j in range(len(labels)) if j != i and cm[i, j]]
        wrong.sort(reverse=True)
        miss = ", ".join("%s %d" % (l2, k) for k, l2 in wrong[:2])
        print("  %-*s %4.0f%%  (%d/%d)%s" % (w, lab, 100 * right / n if n else 0, right, n,
                                            "   mistaken for: " + miss if miss else ""))

    final = RandomForestClassifier(n_estimators=args.trees, min_samples_leaf=2,
                                   class_weight="balanced", random_state=0, n_jobs=-1)
    final.fit(X, y)
    imp = sorted(zip(final.feature_importances_, feats), reverse=True)
    print("\nMost useful features:")
    for v, name in imp[:12]:
        print("  %-14s %.3f" % (name, v))

    final.set_params(n_jobs=1)
    one = X[:1]
    final.predict(one)
    t0 = time.perf_counter()
    for _ in range(50):
        final.predict(one)
    ms = (time.perf_counter() - t0) / 50 * 1000
    print("\nOne prediction on this machine: %.1f ms (krēCHer needs one every 0.5 s)" % ms)

    os.makedirs(os.path.join(HERE, "models"), exist_ok=True)
    out = os.path.join(HERE, "models", datetime.now().strftime("%Y-%m-%d_%H%M") +
                       ("_grouped" if args.grouped else "") + "_rf.joblib")
    joblib.dump({"model": final, "features": feats, "labels": labels, "grouped": args.grouped,
                 "accuracy_unseen": round(acc, 4), "balanced_accuracy_unseen": round(bal, 4),
                 "tested_by": how, "windows": len(y), "sessions": sessions}, out)
    print("Saved %s" % os.path.relpath(out))


if __name__ == "__main__":
    main()
