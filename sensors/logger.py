#!/usr/bin/env python3
"""krēCHer session logger: every sensor in one log, on the Pi's clock.

Logs the BNO085 (IMU), touch module, PIR, ultrasonic, the body link from the Servo 2040
(feet, servo-rail current + voltage, pose), and a camera still every 10 s, into one
JSON-lines file. Either walks you through a test protocol (sensors/protocols.py) and labels
each stretch, or just records while you play with krēCHer ("free" mode).

On the Pi (body link installed on the Servo 2040 first, see docs/data_collection.md):
    cd ~/krecher && source ~/venvs/imu/bin/activate
    python3 sensors/logger.py --check                 # 5 s test of every sensor, nothing saved
    python3 sensors/logger.py                         # full protocol, 3 reps (~15 min)
    python3 sensors/logger.py --protocol floor --reps 1
    python3 sensors/logger.py --free                  # record until Ctrl+C

While a trial runs: type x + Enter = mark this trial bad (dropped later), any other text + Enter
= a note in the log. Ctrl+C at any time: legs go limp, the log and summary are saved.

Free mode: type a label + Enter to start labelling (e.g. picked_up), an empty Enter to stop;
!stand, !crouch, !limp send the body a pose.

Output: data/<date>/<time>_<protocol>.jsonl, a _summary.txt beside it, photos in a _cam/ folder.
Rehearse anywhere, no hardware:  python3 sensors/logger.py --dry-run --yes --time-scale 0.2
"""
import argparse
import json
import math
import os
import queue
import random
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from protocols import PROTOCOLS  # noqa: E402

CHIP = "gpiochip15"          # Pi 5 header (docs/system_map.md)
TOUCH_PIN, PIR_PIN = 17, 4
TRIG_PIN, ECHO_PIN = 27, 22
BODY_PORT = "/dev/ttyACM0"

# What the current trial is, for the simulated sensors in --dry-run (real sensors ignore it).
SIM = {"label": None, "power": True}


# ---------------------------------------------------------------- the log file

class Log:
    """One writer thread; every record gets the Pi's monotonic time `t` (seconds)."""

    def __init__(self, path, keep=False):
        self.path = path
        self.kept = [] if keep else None      # --check: keep records in memory instead
        self.q = queue.Queue()
        self.counts = {}
        self.lock = threading.Lock()
        self.f = open(path, "w") if path else None
        self.thread = threading.Thread(target=self._writer, daemon=True)
        self.thread.start()

    def rec(self, src, **fields):
        r = {"t": round(time.monotonic(), 4), "src": src}
        r.update(fields)
        with self.lock:
            self.counts[src] = self.counts.get(src, 0) + 1
        self.q.put(r)
        return r

    def _writer(self):
        last_flush = time.monotonic()
        while True:
            r = self.q.get()
            if r is None:
                break
            if self.kept is not None:
                self.kept.append(r)
            if self.f:
                self.f.write(json.dumps(r, separators=(",", ":")) + "\n")
                if time.monotonic() - last_flush > 0.5:
                    self.f.flush()
                    last_flush = time.monotonic()
        if self.f:
            self.f.flush()
            self.f.close()

    def close(self):
        self.q.put(None)
        self.thread.join(timeout=5)


def warn(log, src, msg):
    log.rec("err", of=src, msg=str(msg)[:200])


# ---------------------------------------------------------------- real sensors

class Source:
    name = "?"

    def __init__(self):
        self.status = "not started"

    def open(self):          # raise to mark the source unavailable
        pass

    def run(self, log, stop):
        raise NotImplementedError


def to_rpy(i, j, k, r):
    roll = math.atan2(2 * (r * i + j * k), 1 - 2 * (i * i + j * j))
    pitch = math.asin(max(-1.0, min(1.0, 2 * (r * j - k * i))))
    yaw = math.atan2(2 * (r * k + i * j), 1 - 2 * (j * j + k * k))
    return [round(math.degrees(a), 2) for a in (roll, pitch, yaw)]


class IMU(Source):
    """BNO085 on the HAT's I2C port: quaternion (+ roll/pitch/yaw), accel (m/s²), gyro (rad/s)."""
    name = "imu"

    def __init__(self, hz):
        super().__init__()
        self.hz = hz

    def open(self):
        import board
        from adafruit_bno08x import (BNO_REPORT_ACCELEROMETER, BNO_REPORT_GYROSCOPE,
                                     BNO_REPORT_ROTATION_VECTOR)
        from adafruit_bno08x.i2c import BNO08X_I2C
        self.bno = BNO08X_I2C(board.I2C())
        for feat in (BNO_REPORT_ROTATION_VECTOR, BNO_REPORT_ACCELEROMETER, BNO_REPORT_GYROSCOPE):
            self.bno.enable_feature(feat)
        self.bno.quaternion   # first read, so --check fails here if the IMU is missing

    def read(self):
        q = self.bno.quaternion
        a = self.bno.acceleration
        g = self.bno.gyro
        return {"q": [round(x, 5) for x in q], "rpy": to_rpy(*q),
                "acc": [round(x, 3) for x in a], "gyr": [round(x, 4) for x in g]}

    def run(self, log, stop):
        period = 1.0 / self.hz
        nxt = time.monotonic()
        errors = 0
        while not stop.is_set():
            try:
                log.rec("imu", **self.read())
            except Exception as e:
                errors += 1
                if errors <= 5 or errors % 100 == 0:
                    warn(log, "imu", "read error %d: %s" % (errors, e))
            nxt += period
            delay = nxt - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            else:
                nxt = time.monotonic()


class EdgeInput(Source):
    """A digital sensor that drives its pin high when active (touch module, PIR)."""

    def __init__(self, name, pin, debounce=0.02):
        super().__init__()
        self.name, self.pin, self.debounce = name, pin, debounce

    def open(self):
        import gpiod
        self.gpiod = gpiod
        self.chip = gpiod.Chip(CHIP)
        self.line = self.chip.get_line(self.pin)
        self.line.request(consumer="krecher-" + self.name,
                          type=gpiod.LINE_REQ_EV_BOTH_EDGES,
                          flags=gpiod.LINE_REQ_FLAG_BIAS_PULL_DOWN)

    def run(self, log, stop):
        last = self.line.get_value()
        log.rec(self.name, v=last, first=1)
        while not stop.is_set():
            if not self.line.event_wait(0, 200_000_000):
                continue
            self.line.event_read()
            time.sleep(self.debounce)
            while self.line.event_wait(0, 0):
                self.line.event_read()
            v = self.line.get_value()
            if v != last:
                last = v
                log.rec(self.name, v=v)
        self.line.release()


class Ultrasonic(Source):
    """HC-SR04 on 3.3 V. Times the echo with the kernel's edge timestamps, so other threads
    can't stretch the reading. Logs cm, or null when no echo came back."""
    name = "us"

    def __init__(self, hz=10):
        super().__init__()
        self.hz = hz

    def open(self):
        import gpiod
        self.gpiod = gpiod
        chip = gpiod.Chip(CHIP)
        self.trig = chip.get_line(TRIG_PIN)
        self.trig.request(consumer="krecher-us-trig", type=gpiod.LINE_REQ_DIR_OUT)
        self.trig.set_value(0)
        self.echo = chip.get_line(ECHO_PIN)
        self.echo.request(consumer="krecher-us-echo", type=gpiod.LINE_REQ_EV_BOTH_EDGES)

    def measure(self):
        E = self.gpiod.LineEvent
        while self.echo.event_wait(0, 0):              # drop stale edges
            self.echo.event_read()
        self.trig.set_value(1)
        time.sleep(0.00001)
        self.trig.set_value(0)
        rise = None
        deadline = time.monotonic() + 0.06
        while time.monotonic() < deadline:
            if not self.echo.event_wait(0, 10_000_000):
                continue
            ev = self.echo.event_read()
            ts = ev.sec + ev.nsec / 1e9
            if ev.type == E.RISING_EDGE:
                rise = ts
            elif ev.type == E.FALLING_EDGE and rise is not None:
                cm = (ts - rise) * 34300 / 2
                return round(cm, 1) if 2 <= cm <= 450 else None
        return None

    def run(self, log, stop):
        period = 1.0 / self.hz
        while not stop.is_set():
            t0 = time.monotonic()
            try:
                log.rec("us", cm=self.measure())
            except Exception as e:
                warn(log, "us", e)
            time.sleep(max(0.0, period - (time.monotonic() - t0)))


class Body(Source):
    """Servo 2040 over USB serial, running body/main.py (docs/body_link_protocol.md)."""
    name = "body"

    def __init__(self, port=BODY_PORT, hz=50):
        super().__init__()
        self.port, self.hz = port, hz
        self.ser = None
        self.wlock = threading.Lock()
        self.cond = threading.Condition()
        self.events = []          # recent non-sample messages, for wait_for()
        self.hello = None
        self.last_v = None
        self.ping_sent = {}

    def open(self):
        import serial
        self.serial = serial
        self._connect()
        # make sure body/main.py is actually running and answering
        t_end = time.monotonic() + 2.5
        self.send({"k": "hi"})
        while time.monotonic() < t_end:
            line = self.ser.readline()
            if b'"hello"' in line:
                self.hello = json.loads(line.decode(errors="replace"))
                return
        raise RuntimeError("no hello from the Servo 2040: is body/main.py installed? "
                           "(docs/data_collection.md, step 1)")

    def _connect(self):
        self.ser = self.serial.Serial(self.port, 115200, timeout=0.2)
        self.ser.reset_input_buffer()

    def send(self, obj):
        data = (json.dumps(obj) + "\n").encode()
        with self.wlock:
            if self.ser:
                self.ser.write(data)
                self.ser.flush()

    def pose(self, name):
        self.send({"k": "limp"} if name == "limp" else {"k": "pose", "name": name})

    def wait_for(self, kind, name=None, timeout=20.0, since=0.0):
        """Wait for a message (e.g. pose_done) that arrived after `since`. Returns it or None."""
        t_end = time.monotonic() + timeout
        with self.cond:
            while True:
                for t, m in self.events:
                    if t >= since and m.get("k") == kind and (name is None or m.get("name") == name):
                        return m
                left = t_end - time.monotonic()
                if left <= 0:
                    return None
                self.cond.wait(left)

    def _handle(self, log, line):
        t_rx = time.monotonic()
        s = line.decode(errors="replace").strip()
        if not s:
            return
        try:
            m = json.loads(s)
            k = m["k"]
        except Exception:
            log.rec("body_raw", line=s[:200])
            return
        fields = dict(m)
        fields["bt"] = fields.pop("t", None)          # the Servo 2040's own ms clock
        if k == "pong":
            sent = self.ping_sent.pop(m.get("id"), None)
            if sent is not None:
                fields["rtt_ms"] = round((t_rx - sent) * 1000, 2)
        if k == "s":
            self.last_v = m.get("v")
        log.rec("body", **fields)
        if k != "s":
            with self.cond:
                self.events.append((t_rx, m))
                self.events = self.events[-50:]
                self.cond.notify_all()

    def run(self, log, stop):
        self.send({"k": "rate", "hz": self.hz})
        ping_id = 0
        next_ping = time.monotonic()
        while not stop.is_set():
            try:
                if self.ser is None:
                    self._connect()
                    self.send({"k": "hi"})
                    warn(log, "body", "reconnected")
                if time.monotonic() >= next_ping:          # clock check every 10 s
                    ping_id += 1
                    self.ping_sent[ping_id] = time.monotonic()
                    self.send({"k": "ping", "id": ping_id})
                    next_ping += 10
                line = self.ser.readline()
                if line:
                    self._handle(log, line)
            except Exception as e:                        # unplugged / Servo 2040 reset
                warn(log, "body", e)
                try:
                    self.ser.close()
                except Exception:
                    pass
                self.ser = None
                time.sleep(1)
        try:
            self.send({"k": "limp"})
            self.ser.close()
        except Exception:
            pass


class Camera(Source):
    """A still every N seconds with rpicam-still, named by the log clock."""
    name = "cam"

    def __init__(self, folder, every=10.0, width=1280, height=720):
        super().__init__()
        self.folder, self.every, self.w, self.h = folder, every, width, height

    def open(self):
        self.exe = shutil.which("rpicam-still") or shutil.which("libcamera-still")
        if not self.exe:
            raise RuntimeError("rpicam-still not found")

    def run(self, log, stop):
        os.makedirs(self.folder, exist_ok=True)
        nxt = time.monotonic()
        while not stop.is_set():
            t = time.monotonic()
            name = "cam_%010.2f.jpg" % t
            path = os.path.join(self.folder, name)
            try:
                p = subprocess.run([self.exe, "-n", "-t", "300", "--width", str(self.w),
                                    "--height", str(self.h), "-o", path],
                                   capture_output=True, timeout=10)
                if p.returncode == 0:
                    log.rec("cam", file=os.path.join(os.path.basename(self.folder), name),
                            t_shot=round(t, 4), dur=round(time.monotonic() - t, 2))
                else:
                    warn(log, "cam", p.stderr.decode(errors="replace")[-200:])
            except Exception as e:
                warn(log, "cam", e)
            nxt += self.every
            stop.wait(max(0.5, nxt - time.monotonic()))


# ---------------------------------------------------------------- simulated sensors (--dry-run)
# Rough, made-up signals that change with the trial label, so the whole pipeline
# (protocol -> log -> dataset -> model) can be rehearsed and tested without the robot.

class FakeIMU(IMU):
    def open(self):
        self.yaw, self.roll, self.pitch, self.ph = 0.0, 0.0, 0.0, 0.0

    def read(self):
        L = SIM["label"] or ""
        n = lambda s: random.gauss(0, s)  # noqa: E731
        ax, ay, az = n(0.03), n(0.03), 9.81 + n(0.03)
        g = [n(0.005), n(0.005), n(0.005)]
        self.ph += 0.02
        if L in ("shake",):
            ax, ay, az = n(12), n(12), 9.8 + n(12)
            g = [n(4), n(4), n(4)]
        elif L == "carry":
            az += 2.0 * math.sin(self.ph * 2 * math.pi * 1.8) + n(0.6)
            ax += n(0.8); ay += n(0.8)
            g = [n(0.3), n(0.3), 0.2 + n(0.3)]
            self.yaw += 0.4
        elif L == "rotate":
            g = [math.sin(self.ph) + n(0.2), math.cos(self.ph * 0.7) + n(0.2), n(0.5)]
            self.roll = 40 * math.sin(self.ph * 0.6); self.pitch = 30 * math.cos(self.ph * 0.4)
            ax, ay = 9.8 * math.sin(math.radians(self.roll)), 9.8 * math.sin(math.radians(self.pitch))
            ax += n(0.4); ay += n(0.4)
        elif L in ("pick_up", "put_down"):
            az += 3.0 * math.sin(self.ph * 5) + n(0.8); ax += n(0.5); ay += n(0.5)
            g = [n(0.4), n(0.4), n(0.3)]
        elif L == "held_still":
            ax += n(0.15); ay += n(0.15); az += n(0.15); g = [n(0.05), n(0.05), n(0.05)]
        elif L == "bump":
            if random.random() < 0.05:
                ax += n(8); ay += n(8)
            g = [n(0.1), n(0.1), n(0.1)]
        elif L in ("stand_up", "sit_down"):
            az += n(0.3); g = [n(0.05), n(0.08), n(0.02)]
            self.pitch += n(0.3)
        elif L in ("touch_tap", "touch_hold", "pet"):
            ax += n(0.08); ay += n(0.08); az += n(0.1)
        if L not in ("rotate",):
            self.roll *= 0.95; self.pitch *= 0.95
        return {"q": [0, 0, 0, 1], "rpy": [round(self.roll + n(0.1), 2), round(self.pitch + n(0.1), 2),
                                          round(((self.yaw + 180) % 360) - 180, 2)],
                "acc": [round(ax, 3), round(ay, 3), round(az, 3)], "gyr": [round(x, 4) for x in g]}


class FakeEdge(EdgeInput):
    def open(self):
        pass

    def run(self, log, stop):
        last = 0
        log.rec(self.name, v=0, first=1)
        k = 0
        while not stop.is_set():
            time.sleep(0.05)
            k += 1
            L = SIM["label"] or ""
            if self.name == "touch":
                v = {"touch_hold": 1, "touch_tap": int(k % 20 < 4)}.get(L, 0)
            else:
                v = 1 if (L in ("approach", "pass_by") and k % 50 < 35) or \
                    (L in ("pet", "touch_tap", "touch_hold", "bump", "carry", "pick_up",
                           "put_down", "rotate", "shake", "held_still") and k % 60 < 30) else 0
            if v != last:
                last = v
                log.rec(self.name, v=v)


class FakeUltrasonic(Ultrasonic):
    def open(self):
        self.k = 0
        self.label = None

    def measure(self):
        L = SIM["label"] or ""
        if L != self.label:
            self.label, self.k = L, 0
        self.k += 1
        if L == "approach":
            x = abs(((self.k / 25.0) % 2) - 1)
            return round(30 + 170 * x + random.gauss(0, 2), 1)
        if L == "pass_by":
            return round(100 + random.gauss(0, 5), 1) if 20 < self.k % 60 < 40 else None
        if L in ("touch_tap", "touch_hold", "pet", "bump"):
            return round(random.uniform(20, 60), 1)
        if L in ("pick_up", "held_still", "carry", "rotate", "shake", "put_down"):
            return None if random.random() < 0.3 else round(random.uniform(15, 300), 1)
        return None if random.random() < 0.1 else round(240 + random.gauss(0, 2), 1)


class FakeBody(Body):
    def open(self):
        self.pose_name, self.theta, self.n, self.bt0 = "limp", None, 0, time.monotonic()
        self.goal, self.done_at = None, None
        self.scale = 1.0
        self.hello = {"k": "hello", "fw": "fake"}
        self.inbox = queue.Queue()

    def send(self, obj):
        self.inbox.put(obj)

    def run(self, log, stop):
        period = 1.0 / self.hz
        while not stop.is_set():
            now = time.monotonic()
            bt = int((now - self.bt0) * 1000)
            v = 6.0 + random.gauss(0, 0.02) if SIM["power"] else 0.0
            while not self.inbox.empty():
                c = self.inbox.get()
                if c.get("k") == "limp" or c.get("name") == "limp":
                    self.pose_name, self.theta, self.goal = "limp", None, None
                    self._handle(log, json.dumps({"k": "ack", "t": bt, "cmd": "limp", "ok": 1}).encode())
                elif c.get("k") == "pose":
                    if v < 5:
                        self._handle(log, json.dumps({"k": "ack", "t": bt, "cmd": "pose", "ok": 0,
                                                      "msg": "no_servo_power"}).encode())
                    else:
                        self.goal = c["name"]
                        self.done_at = now + 3.0 * self.scale
                        self.pose_name = "moving"
                        self._handle(log, json.dumps({"k": "ack", "t": bt, "cmd": "pose", "ok": 1,
                                                      "name": c["name"]}).encode())
            if self.goal and now >= self.done_at:
                self.pose_name, self.theta = self.goal, {"stand": 10, "crouch": -25}[self.goal]
                self._handle(log, json.dumps({"k": "pose_done", "t": bt, "name": self.goal}).encode())
                self.goal = None
            L = SIM["label"] or ""
            if self.pose_name == "limp" or v < 5:
                a = 0.15 + random.gauss(0, 0.02)
            else:
                a = {"stand": 2.2, "crouch": 1.4, "moving": 3.0}.get(self.pose_name, 2) + random.gauss(0, 0.15)
                if L == "bump" and random.random() < 0.1:
                    a += random.uniform(1, 3)
            self.n += 1
            fv = [0.0] * 6
            self._handle(log, json.dumps({"k": "s", "t": bt, "n": self.n, "feet": [0] * 6, "fv": fv,
                                          "a": round(max(a, 0), 2), "v": round(v, 2),
                                          "p": self.pose_name, "th": self.theta}).encode())
            time.sleep(period)


class FakeCamera(Camera):
    def open(self):
        pass

    def run(self, log, stop):
        while not stop.wait(self.every):
            log.rec("cam", file=None, t_shot=round(time.monotonic(), 4), dur=0, fake=1)


# ---------------------------------------------------------------- voice + keyboard

class Voice:
    def __init__(self, enabled):
        self.q = queue.Queue()
        self.cmd = None
        if enabled:
            if shutil.which("pico2wave") and shutil.which("aplay"):
                self.cmd = "pico"
            elif shutil.which("espeak-ng") or shutil.which("espeak"):
                self.cmd = shutil.which("espeak-ng") or shutil.which("espeak")
            try:
                from fusion_hat.utils import enable_speaker
                enable_speaker()
            except Exception:
                pass
        threading.Thread(target=self._worker, daemon=True).start()

    def say(self, text):
        if self.cmd:
            self.q.put(text)

    def _worker(self):
        while True:
            text = self.q.get()
            try:
                if self.cmd == "pico":
                    wav = "/tmp/krecher_logger_say.wav"
                    subprocess.run(["pico2wave", "-l", "en-US", "-w", wav, text], check=False)
                    subprocess.run(["aplay", "-q", wav], check=False)
                else:
                    subprocess.run([self.cmd, "-s", "150", text], check=False,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass


class Keys:
    """Reads typed lines in the background so trials never block on the keyboard."""

    def __init__(self, enabled):
        self.q = queue.Queue()
        if enabled:
            threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        for line in sys.stdin:
            self.q.put(line.rstrip("\n"))

    def get(self, timeout):
        try:
            return self.q.get(timeout=timeout)
        except queue.Empty:
            return None

    def drain(self):
        out = []
        while not self.q.empty():
            out.append(self.q.get())
        return out


# ---------------------------------------------------------------- session

def git_commit():
    try:
        return subprocess.run(["git", "-C", REPO, "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=3).stdout.strip() or None
    except Exception:
        return None


def build_sources(args, cam_dir):
    if args.dry_run:
        srcs = [FakeIMU(args.imu_hz), FakeEdge("touch", TOUCH_PIN), FakeEdge("pir", PIR_PIN),
                FakeUltrasonic(), FakeBody(hz=args.body_hz)]
        if not args.no_camera:
            srcs.append(FakeCamera(cam_dir, every=args.camera_every))
        return srcs
    srcs = [IMU(args.imu_hz), EdgeInput("touch", TOUCH_PIN), EdgeInput("pir", PIR_PIN),
            Ultrasonic(), Body(args.port, hz=args.body_hz)]
    if not args.no_camera:
        srcs.append(Camera(cam_dir, every=args.camera_every))
    return srcs


def open_sources(srcs):
    live = []
    for s in srcs:
        try:
            s.open()
            s.status = "ok"
            live.append(s)
        except Exception as e:
            s.status = "OFF: %s" % (str(e).splitlines()[0][:120] if str(e) else type(e).__name__)
        print("  %-6s %s" % (s.name, s.status))
    return live


def check(args):
    """--check: open everything, record 5 s into memory, print what each sensor said."""
    print("Checking sensors (nothing is saved)...")
    srcs = build_sources(args, "/tmp/krecher_check_cam")
    live = open_sources(srcs)
    log = Log(None, keep=True)
    stop = threading.Event()
    for s in live:
        threading.Thread(target=s.run, args=(log, stop), daemon=True).start()
    time.sleep(5)
    stop.set()
    time.sleep(0.3)
    seen = {}
    for r in list(log.kept):
        seen.setdefault(r["src"], []).append(r)
    print("\nIn 5 s:")
    for src, rows in sorted(seen.items()):
        last = {k: v for k, v in rows[-1].items() if k not in ("t", "src")}
        print("  %-8s %5d records (%5.1f /s)  last: %s" % (src, len(rows), len(rows) / 5, json.dumps(last)[:110]))
    for s in live:
        if s.name not in seen:
            print("  %-8s nothing came in" % s.name)
    body = next((s for s in live if s.name == "body"), None)
    if body and body.last_v is not None:
        print("\nServo rail: %.2f V (%s)" % (body.last_v, "LiPo in" if body.last_v >= 5 else "no LiPo"))


class Session:
    def __init__(self, args):
        self.args = args
        self.scale = args.time_scale
        stamp = datetime.now()
        day_dir = os.path.join(args.out, stamp.strftime("%Y-%m-%d"))
        os.makedirs(day_dir, exist_ok=True)
        mode = "free" if args.free else args.protocol
        self.id = stamp.strftime("%H%M%S") + "_" + mode + ("_dry" if args.dry_run else "")
        self.path = os.path.join(day_dir, self.id + ".jsonl")
        self.cam_dir = os.path.join(day_dir, self.id + "_cam")
        print("krēCHer logger: session %s" % self.id)
        print("Sensors:")
        self.sources = build_sources(args, self.cam_dir)
        self.live = open_sources(self.sources)
        self.body = next((s for s in self.live if s.name == "body"), None)
        if self.body:
            self.body.scale = self.scale
        self.log = Log(self.path)
        self.log.rec("meta", session=self.id, wall=stamp.isoformat(timespec="seconds"),
                     protocol=mode, reps=args.reps, git=git_commit(), dry_run=bool(args.dry_run),
                     sources={s.name: s.status for s in self.sources},
                     body_fw=(self.body.hello or {}).get("fw") if self.body else None,
                     imu_hz=args.imu_hz, body_hz=args.body_hz, time_scale=self.scale)
        self.stop = threading.Event()
        self.voice = Voice(not args.quiet and not args.dry_run)
        self.keys = Keys(not args.yes)
        self.trials = []          # (rep, block, label, t0, t1, bad)
        self.label = None
        self.cur_bad = False

    def start(self):
        for s in self.live:
            threading.Thread(target=self._guard, args=(s,), daemon=True).start()
        print("Logging to %s\n" % os.path.relpath(self.path, REPO))

    def _guard(self, s):
        try:
            s.run(self.log, self.stop)
        except Exception as e:
            warn(self.log, s.name, "stopped: %s" % e)
            print("!! %s stopped: %s" % (s.name, e))

    def wait(self, secs):
        """Sleep for secs (scaled), handling typed notes / 'x' marks meanwhile."""
        t_end = time.monotonic() + secs * self.scale
        while True:
            left = t_end - time.monotonic()
            if left <= 0:
                return
            line = self.keys.get(min(left, 0.2)) if not self.args.yes else time.sleep(min(left, 0.2))
            if line is None:
                continue
            if line.strip().lower() == "x" and self.label:
                self.log.rec("mark", bad=1, label=self.label)
                self.cur_bad = True
                print("   (marked bad)")
            elif line.strip():
                self.log.rec("note", text=line.strip()[:200], label=self.label)

    def ask(self, prompt):
        print(prompt)
        if self.args.yes:
            return
        self.keys.drain()
        while self.keys.get(0.5) is None:
            pass

    def body_pose(self, name, wait=True):
        if not self.body:
            return None
        since = time.monotonic()
        self.body.pose(name)
        if name == "limp" or not wait:
            return True
        ack = self.body.wait_for("ack", timeout=3, since=since)
        if ack and not ack.get("ok"):
            print("   !! body refused %s: %s" % (name, ack.get("msg")))
            return False
        done = self.body.wait_for("pose_done", name=name, timeout=30 * max(self.scale, 0.2) + 5,
                                  since=since)
        if not done:
            print("   !! body never reported %s reached" % name)
        return bool(done)

    def status_line(self):
        c = self.log.counts
        return "  ".join("%s %d" % (k, c[k]) for k in ("imu", "body", "us", "touch", "pir", "cam", "err")
                         if k in c)

    def run_protocol(self):
        blocks = PROTOCOLS[self.args.protocol]
        for b_i, block in enumerate(blocks):
            SIM["power"] = block["power"]
            print("=" * 64)
            print("BLOCK %s  (%d reps)" % (block["name"].upper(), self.args.reps))
            for line in block["setup"]:
                print("  - " + line)
            if block["power"] and self.body and self.body.last_v is not None and self.body.last_v < 5:
                print("  !! servo rail reads %.1f V: plug the LiPo in for this block." % self.body.last_v)
            self.ask("Press Enter when ready.")
            if not block["power"]:
                self.body_pose("limp")
                time.sleep(0.5)
                if self.body and self.body.last_v is not None and self.body.last_v >= 5:
                    print("  !! servo rail still reads %.1f V. Unplug the LiPo, then Enter." % self.body.last_v)
                    self.ask("")
            for rep in range(1, self.args.reps + 1):
                for i, tr in enumerate(block["trials"], 1):
                    self.run_trial(block, rep, i, tr)
                print("   status: " + self.status_line())
            self.body_pose("limp")
        print("=" * 64 + "\nProtocol finished.")

    def run_trial(self, block, rep, i, tr):
        label = tr["label"]
        n = len(block["trials"])
        secs = tr["secs"]
        print("\n[%s rep %d/%d · %d/%d] %s%s" % (block["name"], rep, self.args.reps, i, n, label.upper(),
                                                "" if secs is None else " (%d s)" % secs))
        print("   " + tr["say"])
        self.voice.say(tr["say"])
        for k in (3, 2, 1):
            print("   %d..." % k, end="\r", flush=True)
            self.wait(1)
        print("   GO     ")
        self.cur_bad = False
        self.label = label
        SIM["label"] = label
        t0 = self.log.rec("label", label=label, edge="start", block=block["name"], rep=rep, trial=i)["t"]
        if tr.get("body"):
            if secs is None:
                ok = self.body_pose(tr["body"])
                if not ok:
                    self.cur_bad = True
                self.wait(0.5)
            else:
                self.body_pose(tr["body"], wait=False)
        if secs is not None:
            self.wait(secs)
        t1 = self.log.rec("label", label=label, edge="end", block=block["name"], rep=rep, trial=i,
                          bad=int(self.cur_bad))["t"]
        self.trials.append((rep, block["name"], label, t0, t1, self.cur_bad))
        self.label = None
        SIM["label"] = None

    def run_free(self):
        print("FREE MODE. Type a label + Enter to start it, empty Enter to stop it.")
        print("!stand / !crouch / !limp move the body. Ctrl+C to finish.\n")
        t0 = None
        while True:
            line = self.keys.get(10)
            if line is None:
                if self.args.yes:
                    time.sleep(1)
                print("   " + self.status_line() + ("   [%s]" % self.label if self.label else ""))
                continue
            line = line.strip()
            if line.startswith("!"):
                print("   body:", line[1:], "->", self.body_pose(line[1:], wait=False))
                continue
            if self.label:
                t1 = self.log.rec("label", label=self.label, edge="end", block="free")["t"]
                self.trials.append((0, "free", self.label, t0, t1, False))
                print("   end %s (%.1f s)" % (self.label, t1 - t0))
                self.label = SIM["label"] = None
            if line:
                self.label = SIM["label"] = line.lower().replace(" ", "_")
                t0 = self.free_t0 = self.log.rec("label", label=self.label, edge="start", block="free")["t"]
                print("   start %s" % self.label)

    def finish(self, aborted):
        if self.label and self.args.free:          # Ctrl+C is how free mode ends
            t1 = self.log.rec("label", label=self.label, edge="end", block="free")["t"]
            self.trials.append((0, "free", self.label, self.free_t0, t1, False))
        elif self.label:
            self.log.rec("label", label=self.label, edge="end", aborted=1, bad=1)
        if self.body:
            try:
                self.body.pose("limp")
            except Exception:
                pass
        time.sleep(0.3)
        self.stop.set()
        time.sleep(0.5)
        counts = dict(self.log.counts)
        self.log.rec("meta_end", aborted=int(aborted), counts=counts)
        self.log.close()
        self.write_summary(aborted)

    def write_summary(self, aborted):
        rows = []
        with open(self.path) as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
        lines = ["krēCHer session %s%s" % (self.id, "  (STOPPED EARLY)" if aborted else ""),
                 "file: %s" % os.path.relpath(self.path, REPO), ""]
        if rows:
            span = rows[-1]["t"] - rows[0]["t"]
            lines.append("length: %.0f s" % span)
            by = {}
            for r in rows:
                by.setdefault(r["src"], []).append(r)
            for src in ("imu", "body", "us", "touch", "pir", "cam"):
                rs = by.get(src, [])
                if not rs:
                    lines.append("  %-6s none" % src)
                    continue
                if src in ("imu", "us") or (src == "body"):
                    if src == "body":
                        rs = [r for r in rs if r.get("k") == "s"]
                    rate = len(rs) / span if span else 0
                    gaps = sorted(b["t"] - a["t"] for a, b in zip(rs, rs[1:]))
                    worst = gaps[-1] if gaps else 0
                    extra = ""
                    if src == "body" and rs:
                        ns = [r["n"] for r in rs]
                        lost = sum(max(0, b - a - 1) for a, b in zip(ns, ns[1:]))
                        vs = [r["v"] for r in rs]
                        amps = [r["a"] for r in rs]
                        extra = "  lost %d  rail %.1f-%.1f V  current max %.2f A" % (
                            lost, min(vs), max(vs), max(amps))
                    if src == "us":
                        ok = [r["cm"] for r in rs if r.get("cm") is not None]
                        extra = "  echoes %d%%" % (100 * len(ok) / len(rs))
                    lines.append("  %-6s %6d  %5.1f /s  longest gap %.2f s%s" % (src, len(rs), rate, worst, extra))
                else:
                    on = sum(1 for r in rs if r.get("v") == 1)
                    lines.append("  %-6s %6d records%s" % (src, len(rs), "  (%d on)" % on if src != "cam" else ""))
            errs = by.get("err", [])
            lines.append("  errors %d" % len(errs))
            for e in errs[:8]:
                lines.append("    %s: %s" % (e.get("of"), e.get("msg")))
            pongs = [r["rtt_ms"] for r in by.get("body", []) if r.get("k") == "pong" and "rtt_ms" in r]
            if pongs:
                lines.append("  body link round trip: median %.1f ms" % sorted(pongs)[len(pongs) // 2])
        lines.append("")
        lines.append("trials: %d  (bad %d)" % (len(self.trials), sum(1 for t in self.trials if t[5])))
        tally = {}
        for rep, block, label, t0, t1, bad in self.trials:
            d = tally.setdefault(label, [0, 0.0, 0])
            d[0] += 1
            d[1] += t1 - t0
            d[2] += int(bad)
        for label, (k, secs, bad) in tally.items():
            lines.append("  %-14s x%d  %6.1f s%s" % (label, k, secs, "  (%d bad)" % bad if bad else ""))
        text = "\n".join(lines) + "\n"
        with open(self.path.replace(".jsonl", "_summary.txt"), "w") as f:
            f.write(text)
        print("\n" + text)


def main():
    ap = argparse.ArgumentParser(description="Log all of krēCHer's sensors on one clock.")
    ap.add_argument("--protocol", default="full", choices=sorted(PROTOCOLS))
    ap.add_argument("--reps", type=int, default=3, help="repeats of each block (default 3)")
    ap.add_argument("--free", action="store_true", help="no protocol: record + label by typing")
    ap.add_argument("--check", action="store_true", help="5 s sensor check, nothing saved")
    ap.add_argument("--imu-hz", type=float, default=50)
    ap.add_argument("--body-hz", type=int, default=50)
    ap.add_argument("--camera-every", type=float, default=10.0, help="seconds between stills")
    ap.add_argument("--no-camera", action="store_true")
    ap.add_argument("--port", default=BODY_PORT)
    ap.add_argument("--quiet", action="store_true", help="don't speak the instructions")
    ap.add_argument("--out", default=os.path.join(REPO, "data"))
    ap.add_argument("--dry-run", action="store_true", help="simulated sensors, for rehearsing/testing")
    ap.add_argument("--yes", action="store_true", help="don't wait for Enter (unattended / testing)")
    ap.add_argument("--time-scale", type=float, default=1.0, help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.check:
        check(args)
        return
    s = Session(args)
    if not any(x.name == "imu" for x in s.live) and not args.dry_run:
        print("\n!! The IMU is off. Most of what krēCHer learns comes from it. Fix it first "
              "(run with --check).")
        if not args.yes:
            s.ask("Enter to log anyway, Ctrl+C to stop.")
    s.start()
    aborted = False
    try:
        if args.free:
            s.run_free()
        else:
            s.run_protocol()
    except KeyboardInterrupt:
        aborted = not args.free
        print("\nStopping: legs going limp, saving the log...")
    finally:
        s.finish(aborted)


if __name__ == "__main__":
    main()
