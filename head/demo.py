"""krēCHer's demo program (core, Nov 5): wake, say hi, purr / flinch, how are you feeling,
goodbye, all driven from an operator page on your phone.

Run on the Pi, from the IMU/head venv:
    source ~/venvs/imu/bin/activate
    python ~/krecher/head/demo.py              # everything
    python ~/krecher/head/demo.py --no-body    # head, face and sensors only (LiPo out, no legs)

Then open the operator page on your phone or Mac (Tailscale on):
    http://100.75.140.37:8001        operator buttons
    http://100.75.140.37:8001/tv     the TV screen: QR code, face, hearts

The audience page (hearts + krēCHer's camera) is on port 8000; the volunteer's driver page is
/driver on the same port (the driver code is on the operator page).
The camera comes from rpicam-vid (nothing to install). Only one program can use the camera, so
don't run logger.py or rpicam-hello while this runs. Upside-down picture: --cam-rotation 180. To reach it from anyone's phone, turn Funnel on
for the demo, and off after:
    sudo tailscale funnel --bg 8000
    sudo tailscale funnel reset          (check: tailscale funnel status -> "No serve config")

Needs:
  * body/main.py v0.3 on the Servo 2040 (for the wave / duck gestures). Install once, LiPo out:
        source ~/venvs/servo/bin/activate
        mpremote connect /dev/ttyACM0 cp ~/krecher/body/main.py :main.py + reset
  * Nothing else may use /dev/ttyACM0 (no logger.py, no mpremote) while this runs.

Ctrl+C: the legs go limp, the head re-centres, the face goes dark.

Later layers (Fri/Sat): face recognition (replaces the "known" switch), head tracking,
remote page, hearts, story mode, memories, voice commands.
"""
import argparse
import json
import math
import os
import queue
import random
import shutil
import struct
import subprocess
import sys
import threading
import time
import wave
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from face import Face, say as face_say          # noqa: E402

PORT_BODY = "/dev/ttyACM0"
CHIP = "gpiochip15"
TOUCH_PIN, PIR_PIN, TRIG, ECHO = 17, 4, 27, 22
OPERATOR_PORT = 8001
AUDIENCE_PORT = 8000
HEARTS_TO_PURR, HEARTS_WINDOW_S, HEARTS_PURR_GAP_S = 5, 3.0, 12.0
DRIVER_TIMEOUT_S = 10.0          # a driver who stops polling for this long loses control
MAX_WATCH_STREAMS = 10           # live video for this many watchers; the rest get a still every few s
GREETING = "Hello! I'm krēCHer."
GOODBYE = "Goodbye, everyone! Thank you for meeting me."
PURR_WAV = "/tmp/krecher_purr.wav"


def log(*a):
    print(time.strftime("[%H:%M:%S]"), *a, flush=True)


# ---------------------------------------------------------------- head (pan-tilt)
class Head:
    PAN = (-45, 45)
    TILT = (-15, 12)

    def __init__(self):
        self.p = self.t = 0.0
        self.ok = False
        try:
            from fusion_hat.servo import Servo
            self.pan, self.tilt = Servo(2), Servo(3)        # PWM 2 = pan, PWM 3 = tilt
            self.ok = True
        except Exception as e:
            log("head: pan-tilt not available (%s)" % e)

    def move(self, p, t, secs=0.8):
        p = max(self.PAN[0], min(self.PAN[1], p))
        t = max(self.TILT[0], min(self.TILT[1], t))
        steps = max(1, int(secs / 0.03))
        p0, t0 = self.p, self.t
        for i in range(1, steps + 1):
            f = i / steps
            f = f * f * (3 - 2 * f)
            if self.ok:
                self.pan.angle(round(p0 + (p - p0) * f, 1))
                self.tilt.angle(round(t0 + (t - t0) * f, 1))
            time.sleep(0.03)
        self.p, self.t = p, t


# ---------------------------------------------------------------- body (Servo 2040, main.py)
class Body:
    def __init__(self, enabled=True):
        self.ser = None
        self.v = None              # servo rail voltage (None = no samples yet)
        self.pose = "?"
        self.fw = None
        self._cv = threading.Condition()
        self._seen = {}            # (kind, name) -> (time, message)
        if not enabled:
            log("body: off (--no-body)")
            return
        if not os.path.exists(PORT_BODY):
            log("body: Servo 2040 not found at %s (USB unplugged?). Running head-only." % PORT_BODY)
            return
        try:
            import serial
            self.ser = serial.Serial(PORT_BODY, 115200, timeout=0.2)
        except Exception as e:
            log("body: can't open %s (%s). Is logger.py or mpremote using it?" % (PORT_BODY, e))
            return
        threading.Thread(target=self._reader, daemon=True).start()
        self.send({"k": "hi"})
        if not self._wait("hello", None, 2.5):
            log("body: no answer from main.py. Unplug and replug the Servo 2040's USB, then restart.")
        elif not (self.fw or "").endswith("0.3"):
            log("body: main.py is %s; the wave and flinch need 0.3 (see the top of this file)." % self.fw)

    @property
    def ok(self):
        return self.ser is not None

    def send(self, obj):
        if self.ser:
            self.ser.write((json.dumps(obj) + "\n").encode())

    def _reader(self):
        buf = b""
        while True:
            try:
                buf += self.ser.read(256)
            except Exception as e:
                log("body: serial error (%s)" % e)
                time.sleep(1)
                continue
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                try:
                    m = json.loads(line)
                except ValueError:
                    continue
                k = m.get("k")
                if k == "s":
                    self.v, self.pose = m.get("v"), m.get("p", self.pose)
                    continue
                if k == "hello":
                    self.fw = m.get("fw")
                if k == "w":
                    log("body warning:", m)
                with self._cv:
                    key = (k, m.get("name") or m.get("cmd"))
                    self._seen[key] = (time.monotonic(), m)
                    self._seen[(k, None)] = (time.monotonic(), m)
                    self._cv.notify_all()

    def _wait(self, kind, name, timeout, since=None):
        since = time.monotonic() - 0.01 if since is None else since
        end = time.monotonic() + timeout
        with self._cv:
            while True:
                got = self._seen.get((kind, name))
                if got and got[0] >= since:
                    return got[1]
                left = end - time.monotonic()
                if left <= 0:
                    return None
                self._cv.wait(left)

    def _command(self, cmd, done_kind, name, timeout):
        """Send, check the ack, wait for done. Returns True when done."""
        if not self.ser:
            return False
        t0 = time.monotonic()
        self.send(cmd)
        ack = self._wait("ack", name, 1.5, t0)
        if ack is None or not ack.get("ok"):
            log("body: %s %s refused (%s)" % (cmd["k"], name, (ack or {}).get("msg", "no ack")))
            return False
        return self._wait(done_kind, name, timeout, t0) is not None

    def pose_to(self, name, timeout=15):
        return self._command({"k": "pose", "name": name}, "pose_done", name, timeout)

    def gesture(self, name, wait=True, timeout=10):
        if not wait:
            threading.Thread(target=self._command,
                             args=({"k": "gesture", "name": name}, "gesture_done", name, timeout),
                             daemon=True).start()
            return True
        return self._command({"k": "gesture", "name": name}, "gesture_done", name, timeout)

    def limp(self):
        self.send({"k": "limp"})


# ---------------------------------------------------------------- senses (touch, PIR, ultrasonic, battery)
class Senses:
    def __init__(self, on_touch, on_motion):
        self.on_touch, self.on_motion = on_touch, on_motion
        self.dist = None                        # cm, None = nothing in range
        self.motion = deque(maxlen=50)          # PIR event times
        self.touches = deque(maxlen=50)
        self.started = time.monotonic()
        self.battery = None
        try:
            import gpiod
            self.gpiod = gpiod
        except Exception as e:
            log("senses: gpiod not available (%s)" % e)
            self.gpiod = None
            return
        for pin, name, cb in ((TOUCH_PIN, "touch", self._touch), (PIR_PIN, "pir", self._pir)):
            threading.Thread(target=self._watch, args=(pin, name, cb), daemon=True).start()
        threading.Thread(target=self._ultrasonic, daemon=True).start()
        threading.Thread(target=self._battery, daemon=True).start()

    def _watch(self, pin, name, cb):
        gpiod = self.gpiod
        try:
            line = gpiod.Chip(CHIP).get_line(pin)
            line.request(consumer="krecher-demo-" + name, type=gpiod.LINE_REQ_EV_BOTH_EDGES,
                         flags=gpiod.LINE_REQ_FLAG_BIAS_PULL_DOWN)
        except Exception as e:
            log("senses: %s on GPIO%d not available (%s)" % (name, pin, e))
            return
        state = line.get_value()
        while True:
            if not line.event_wait(1, 0):
                continue
            line.event_read()
            time.sleep(0.02)
            while line.event_wait(0, 0):
                line.event_read()
            new = line.get_value()
            if new != state:
                state = new
                if new:
                    cb()

    def _touch(self):
        self.touches.append(time.monotonic())
        self.on_touch()

    def _pir(self):
        if time.monotonic() - self.started < 45:     # PIR warm-up
            return
        self.motion.append(time.monotonic())
        self.on_motion()

    def _ultrasonic(self):
        gpiod = self.gpiod
        try:
            chip = gpiod.Chip(CHIP)
            trig = chip.get_line(TRIG)
            trig.request(consumer="krecher-demo-trig", type=gpiod.LINE_REQ_DIR_OUT)
            trig.set_value(0)
            echo = chip.get_line(ECHO)
            echo.request(consumer="krecher-demo-echo", type=gpiod.LINE_REQ_DIR_IN)
        except Exception as e:
            log("senses: ultrasonic not available (%s)" % e)
            return

        def measure():
            to = 0.03
            t0 = time.perf_counter()
            while echo.get_value() == 1:
                if time.perf_counter() - t0 > to:
                    return None
            trig.set_value(1); time.sleep(0.00001); trig.set_value(0)
            t0 = time.perf_counter()
            while echo.get_value() == 0:
                if time.perf_counter() - t0 > to:
                    return None
            s = time.perf_counter()
            while echo.get_value() == 1:
                if time.perf_counter() - s > to:
                    return None
            return (time.perf_counter() - s) * 34300 / 2

        while True:
            vals = []
            for _ in range(3):
                d = measure()
                if d is not None and d < 400:
                    vals.append(d)
                time.sleep(0.04)
            self.dist = sorted(vals)[len(vals) // 2] if vals else None
            time.sleep(0.1)

    def _battery(self):
        """The head's 2S battery, if the HAT library can read it."""
        try:
            import fusion_hat.device as dev
            fn = next((getattr(dev, n) for n in dir(dev)
                       if "batt" in n.lower() and "volt" in n.lower()), None)
        except Exception:
            fn = None
        if not fn:
            log("senses: no battery reading in fusion_hat.device (the feeling sentence skips it)")
            return
        import contextlib, io, warnings
        while True:
            try:
                with warnings.catch_warnings(), contextlib.redirect_stdout(io.StringIO()), \
                        contextlib.redirect_stderr(io.StringIO()):
                    warnings.simplefilter("ignore")      # the HAT library prints a deprecation note
                    v = float(fn())
                self.battery = max(0, min(100, round((v - 6.4) / (8.4 - 6.4) * 100)))
            except Exception:
                pass
            time.sleep(30)

    def recent(self, dq, secs):
        now = time.monotonic()
        return sum(1 for t in dq if now - t < secs)


# ---------------------------------------------------------------- sounds
def make_purr():
    """A short purr: a low buzz pulsing about 24 times a second."""
    if os.path.exists(PURR_WAV):
        return
    rate, secs = 16000, 2.5
    frames = bytearray()
    rnd = random.Random(7)
    for i in range(int(rate * secs)):
        t = i / rate
        env = (0.5 + 0.5 * math.sin(2 * math.pi * 24 * t)) ** 3          # purr pulses
        fade = min(1, t / 0.3, (secs - t) / 0.4)
        x = (0.55 * math.sin(2 * math.pi * 130 * t) + 0.3 * math.sin(2 * math.pi * 260 * t)
             + 0.25 * (rnd.random() * 2 - 1))
        frames += struct.pack("<h", int(9000 * env * fade * x))
    with wave.open(PURR_WAV, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(bytes(frames))


def play(path):
    try:
        return subprocess.Popen(["aplay", "-q", path])
    except Exception as e:
        log("sound: can't play %s (%s)" % (path, e))


# ---------------------------------------------------------------- camera (rpicam-vid MJPEG)
class Camera:
    """krēCHer's eye. rpicam-vid streams JPEG frames on stdout; we keep the latest one."""

    def __init__(self, enabled=True, width=640, height=480, fps=12, rotation=0):
        self.jpeg = None
        self.n = 0
        self.cv = threading.Condition()
        self.proc = None
        self.ok = False
        if not enabled:
            log("camera: off (--no-camera)")
            return
        exe = shutil.which("rpicam-vid") or shutil.which("libcamera-vid")
        if not exe:
            log("camera: rpicam-vid not found, no video")
            return
        self.cmd = [exe, "-t", "0", "-n", "--codec", "mjpeg", "--width", str(width),
                    "--height", str(height), "--framerate", str(fps), "--quality", "70", "-o", "-"]
        if rotation:
            self.cmd += ["--rotation", str(rotation)]
        self.ok = True
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        fails = 0
        while fails < 5:
            started = time.monotonic()
            try:
                self.proc = subprocess.Popen(self.cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except Exception as e:
                log("camera: can't start rpicam-vid (%s)" % e)
                break
            buf = b""
            while True:
                chunk = self.proc.stdout.read1(65536)
                if not chunk:
                    break
                buf += chunk
                while True:
                    a = buf.find(b"\xff\xd8")
                    if a < 0:
                        buf = b""
                        break
                    b = buf.find(b"\xff\xd9", a + 2)
                    if b < 0:
                        buf = buf[a:]
                        break
                    with self.cv:
                        self.jpeg = buf[a:b + 2]
                        self.n += 1
                        self.cv.notify_all()
                    buf = buf[b + 2:]
                if len(buf) > 2_000_000:
                    buf = b""
            err = (self.proc.stderr.read() or b"").decode(errors="ignore").strip().splitlines()[-2:]
            log("camera: rpicam-vid stopped (%s). Is another program using the camera?" % " / ".join(err))
            fails = 0 if time.monotonic() - started > 30 else fails + 1
            time.sleep(2)
        self.ok = False
        log("camera: giving up")

    def wait(self, last_n, timeout=2.0):
        with self.cv:
            self.cv.wait_for(lambda: self.n != last_n, timeout)
            return self.n, self.jpeg

    def close(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()


# ---------------------------------------------------------------- audience (hearts)
class Audience:
    """Everyone who scans the QR code: they see krēCHer's face and can send hearts."""

    def __init__(self, k):
        self.k = k
        self.enabled = True
        self.hearts = deque(maxlen=2000)        # heart times
        self.last_heart = {}                    # client id -> time (1 heart per second each)
        self.seen = {}                          # client id -> last poll time
        self.last_purr = 0.0

    def poll(self, cid):
        if cid:
            self.seen[cid[:40]] = time.monotonic()

    def viewers(self):
        now = time.monotonic()
        return sum(1 for t in list(self.seen.values()) if now - t < 10)

    def recent(self, secs):
        now = time.monotonic()
        return sum(1 for t in list(self.hearts) if now - t < secs)

    def heart(self, cid):
        k = self.k
        if not self.enabled:
            return "off"
        if k.state != "awake":
            return "asleep"
        now = time.monotonic()
        cid = (cid or "?")[:40]
        if now - self.last_heart.get(cid, 0) < 1.0:
            return "slow down"
        self.last_heart[cid] = now
        self.seen[cid] = now
        self.hearts.append(now)
        k.face.pulse()
        k.alarm = max(0.0, k.alarm - 0.05)
        if (self.recent(HEARTS_WINDOW_S) >= HEARTS_TO_PURR and not k.busy
                and now - self.last_purr > HEARTS_PURR_GAP_S):
            self.last_purr = now
            k.do("hearts_purr")
        return "ok"


# ---------------------------------------------------------------- krēCHer
class Krecher:
    def __init__(self, use_body=True, use_camera=True, cam_rotation=0):
        self.face = Face()
        self.face.set("sleep")
        self.head = Head()
        self.head.move(0, -10, 0.5)                     # sleeping: head down
        self.body = Body(use_body)
        self.state = "asleep"                           # asleep | awake
        self.known = True                               # operator switch until face recognition
        self.alarm = 0.0                                # 0 calm .. 1 alarmed
        self.curious = 0.0                              # -1 wary .. 1 curious
        self.busy = False
        self.last = ""                                  # last thing done, for the operator page
        self.history = deque(maxlen=20)                 # (time, event) for the feeling sentence
        self.actions = queue.Queue()
        self.audience = Audience(self)
        self.camera = Camera(use_camera, rotation=cam_rotation)
        self.watch_streams = 0                          # live video streams to watchers
        self.driver = None                              # {"id": ..., "seen": t} while someone drives
        self.driver_code = "%04d" % random.randint(0, 9999)
        self.head_target = None                         # (pan, tilt) the driver asked for
        self.pan_sign = 1                               # flip from the operator page if drag goes the wrong way
        self.touch_count = 0
        self.last_message = ""
        try:
            from fusion_hat.device import enable_speaker
            enable_speaker()
        except Exception:
            pass
        make_purr()
        self.senses = Senses(self._on_touch, self._on_motion)
        threading.Thread(target=self._worker, daemon=True).start()
        threading.Thread(target=self._mood_loop, daemon=True).start()
        threading.Thread(target=self._remote_loop, daemon=True).start()

    # ---- actions: one at a time, in order -------------------------------------
    def do(self, name, **kw):
        fn = getattr(self, "act_" + name, None)
        if not fn:
            return False
        self.actions.put((name, fn, kw))
        return True

    def _worker(self):
        while True:
            name, fn, kw = self.actions.get()
            self.busy = True
            self.last = name
            log("action:", name, kw or "")
            try:
                fn(**kw)
            except Exception as e:
                log("action %s failed: %s" % (name, e))
            finally:
                self.busy = False

    def say(self, text):
        face_say(text, self.face)

    def act_wake(self):
        if self.state == "awake":
            return
        self.face.set("awake")
        self.state = "awake"
        self.alarm, self.curious = 0.0, 0.3
        self.head.move(0, 8, 1.2)                       # looks up
        if self.body.ok:
            standing = threading.Thread(target=self.body.pose_to, args=("stand",))
            standing.start()
            for p, t in ((-30, 5), (30, 5), (0, 8)):     # looks around while it gets up
                self.head.move(p, t, 1.4)
                time.sleep(0.4)
            standing.join()
        else:
            self.head.move(-30, 5, 1.2); self.head.move(30, 5, 1.6); self.head.move(0, 8, 1.0)

    def act_hi(self):
        if self.state != "awake":
            self.act_wake()
        t0 = time.monotonic()
        waving = self.body.ok and self.body.pose == "stand" and self.body.gesture("wave", wait=False)
        if waving:
            time.sleep(1.4)                             # leg is up
        self.face.set("awake")
        self.head.move(0, 10, 0.5)
        self.say(GREETING)
        self.history.append((time.monotonic(), "hi"))
        if waving:
            self.body._wait("gesture_done", "wave", 8, t0)

    def act_feeling(self):
        self.head.move(0, 8, 0.5)
        text = self.feeling_sentence()
        log("feeling:", text)
        self.say(text)

    def act_purr(self):
        self.face.set("purr")
        snd = play(PURR_WAV)
        for _ in range(2):                              # nods
            self.head.move(self.head.p, -6, 0.35)
            self.head.move(self.head.p, 6, 0.35)
        self.head.move(self.head.p, 4, 0.3)
        if snd:
            snd.wait()
        self.alarm = max(0.0, self.alarm - 0.6)
        self.curious = min(1.0, self.curious + 0.2)
        self.history.append((time.monotonic(), "purr"))
        time.sleep(0.5)

    def act_hearts_purr(self):
        """Lots of hearts at once: krēCHer melts."""
        self.face.set("love")
        snd = play(PURR_WAV)
        self.head.move(-15, 10, 0.8)                    # looks out over the audience
        self.head.move(15, 10, 1.4)
        self.head.move(0, 8, 0.8)
        if snd:
            snd.wait()
        self.alarm = 0.0
        self.curious = min(1.0, self.curious + 0.3)
        self.history.append((time.monotonic(), "hearts"))
        time.sleep(0.8)

    def act_flinch(self):
        self.face.set("flinch")
        self.alarm, self.curious = 1.0, -0.8
        side = random.choice((-1, 1))
        if self.body.ok and self.body.pose == "stand":
            self.body.gesture("duck", wait=False)
        self.head.move(35 * side, -12, 0.25)            # pulls back and looks away
        self.history.append((time.monotonic(), "flinch"))
        time.sleep(1.5)
        self.face.set("cautious")
        self.face.look(-side, 0)                        # eyes peek back
        time.sleep(1.0)
        self.head.move(10 * side, 0, 2.0)               # slowly turns back, still wary
        self.face.look(0, 0)

    def act_goodbye(self):
        self.face.set("awake")
        t0 = time.monotonic()
        waving = self.body.ok and self.body.pose == "stand" and self.body.gesture("wave", wait=False)
        if waving:
            time.sleep(1.4)
        self.head.move(0, 10, 0.5)
        self.say(GOODBYE)
        if waving:
            self.body._wait("gesture_done", "wave", 8, t0)
        self.act_sleep()

    def act_sleep(self):
        if self.body.ok and self.body.pose in ("stand", "gesture", "moving"):
            self.body.pose_to("crouch")
            time.sleep(0.5)
            self.body.limp()
        self.state = "asleep"
        self.face.set("sleep")
        self.head.move(0, -10, 1.5)

    def act_say(self, text=""):
        if text.strip():
            self.say(text.strip()[:200])

    def act_stand(self):
        self.body.pose_to("stand")

    def act_crouch(self):
        self.body.pose_to("crouch")

    def act_center(self):
        self.head.move(0, 0, 0.6)

    def act_test_face(self):
        for name in ("awake", "curious", "cautious", "purr", "flinch", "shy", "love", "calm"):
            self.face.set(name)
            time.sleep(1.2)

    def emergency_limp(self):
        """Not queued: runs right away."""
        self.body.limp()
        log("LIMP (operator)")

    # ---- remote driver ----------------------------------------------------------
    def driver_active(self):
        return self.driver is not None and time.monotonic() - self.driver["seen"] < DRIVER_TIMEOUT_S

    def is_driver(self, cid):
        return bool(cid) and self.driver_active() and self.driver["id"] == cid

    def claim(self, cid, code):
        if not cid:
            return "error"
        if str(code).strip() != self.driver_code:
            return "wrong code"
        if self.driver_active() and self.driver["id"] != cid:
            return "busy"
        self.driver = {"id": cid, "seen": time.monotonic()}
        self.head_target = (self.head.p, self.head.t)
        log("remote: driver connected")
        self.history.append((time.monotonic(), "driver"))
        return "ok"

    def driver_seen(self, cid):
        if self.is_driver(cid):
            self.driver["seen"] = time.monotonic()

    def look(self, cid, pan, tilt):
        if not self.is_driver(cid):
            return False
        self.head_target = (max(Head.PAN[0], min(Head.PAN[1], float(pan))),
                            max(Head.TILT[0], min(Head.TILT[1], float(tilt))))
        return True

    def release_driver(self, new_code=False):
        if self.driver:
            log("remote: driver released")
        self.driver = None
        self.head_target = None
        if new_code:
            self.driver_code = "%04d" % random.randint(0, 9999)

    def _remote_loop(self):
        was = False
        while True:
            time.sleep(0.05)
            active = self.driver_active()
            if was and not active and self.driver is not None:
                log("remote: driver gone (no contact for %d s), control is free" % DRIVER_TIMEOUT_S)
                self.driver, self.head_target = None, None
            was = active
            tgt = self.head_target
            if not active or not tgt or self.busy:
                continue
            p, t = tgt
            if abs(p - self.head.p) > 0.5 or abs(t - self.head.t) > 0.5:
                step_p = max(-6, min(6, p - self.head.p))       # at most 6 degrees per tick
                step_t = max(-6, min(6, t - self.head.t))
                self.head.move(self.head.p + step_p, self.head.t + step_t, 0.06)

    def act_remote_say(self, text=""):
        text = text.strip()[:120]
        if not text:
            return
        self.last_message = text
        self.history.append((time.monotonic(), "message"))
        self.say(text)

    def act_purr_soft(self):
        """Petted while someone is driving: purr and glow, but leave the head to the driver."""
        self.face.set("purr")
        snd = play(PURR_WAV)
        if snd:
            snd.wait()
        self.alarm = max(0.0, self.alarm - 0.6)
        self.history.append((time.monotonic(), "purr"))

    # ---- reflexes ---------------------------------------------------------------
    def _on_touch(self):
        self.touch_count += 1
        log("touch", "(known)" if self.known else "(stranger)")
        if self.driver_active():
            if not self.busy:
                self.do("purr_soft")
            return
        if self.state == "asleep":
            if not self.busy:
                self.do("wake")
            return
        if self.busy:
            return
        self.do("purr" if self.known else "flinch")

    def _on_motion(self):
        if self.state != "awake":
            return
        self.curious = min(1.0, self.curious + 0.25)
        if not self.known:
            self.alarm = min(1.0, self.alarm + 0.1)
        if not self.busy:
            self.face.look(random.choice((-0.8, 0.8)), 0)

    def _mood_loop(self):
        last_d = None
        while True:
            time.sleep(0.2)
            # dials drift back towards calm
            self.alarm *= 0.985
            self.curious += (0.1 - self.curious) * 0.01
            d = self.senses.dist
            if self.state == "awake" and d is not None and d < 50 and (last_d is None or d < last_d - 2):
                if self.known:                           # someone comes close
                    self.curious = min(1.0, self.curious + 0.05)
                else:
                    self.alarm = min(1.0, self.alarm + 0.04)
            last_d = d
            if self.busy or self.state != "awake":
                continue
            self.face.set(self.mood_expression())
            if random.random() < 0.02:                   # eyes wander now and then
                self.face.look(random.uniform(-0.6, 0.6), random.uniform(-0.3, 0.3))

    def mood_expression(self):
        if self.alarm > 0.5:
            return "cautious"
        if self.alarm > 0.25 and self.curious < 0:
            return "cautious"
        if self.curious > 0.5:
            return "curious"
        return "calm"

    def feeling_sentence(self):
        now = time.monotonic()
        recent = [e for t, e in self.history if now - t < 180]
        parts = []
        if self.alarm > 0.6:
            parts.append("I'm a little scared right now.")
        elif self.alarm > 0.3:
            parts.append("I'm a bit nervous.")
        elif self.curious > 0.4:
            parts.append("I'm curious. There's a lot to look at.")
        else:
            parts.append("I'm calm. I feel good.")
        if "hearts" in recent or self.audience.recent(120) >= 3:
            parts.append("So many of you are sending me hearts. I can feel it in my lights.")
        if "flinch" in recent:
            parts.append("Someone I don't know touched me, and it startled me.")
        elif "purr" in recent:
            parts.append("Someone petted me, and I liked that.")
        moves = self.senses.recent(self.senses.motion, 60)
        if moves >= 3:
            parts.append("Things keep moving around me. I think there are a lot of people here.")
        elif moves >= 1:
            parts.append("Someone is moving near me.")
        d = self.senses.dist
        if d is not None and d < 60:
            parts.append("Someone is very close to me.")
        elif d is not None and d < 250:
            feet = max(2, round(d / 30.48))
            parts.append("Someone is about %d feet away." % feet)
        if self.senses.battery is not None:
            parts.append("My battery is at %d percent." % self.senses.battery)
        return " ".join(parts)

    def status(self):
        d = self.senses.dist
        return {
            "state": self.state, "busy": self.busy, "last": self.last, "known": self.known,
            "alarm": round(self.alarm, 2), "curious": round(self.curious, 2),
            "face": self.face.expr,
            "dist_in": None if d is None else round(d / 2.54),
            "motion_60s": self.senses.recent(self.senses.motion, 60),
            "touches_60s": self.senses.recent(self.senses.touches, 60),
            "battery": self.senses.battery,
            "body": {"ok": self.body.ok, "pose": self.body.pose,
                     "rail_v": None if self.body.v is None else round(self.body.v, 2),
                     "fw": self.body.fw},
            "queue": self.actions.qsize(),
            "audience": {"hearts_on": self.audience.enabled, "viewers": self.audience.viewers(),
                         "hearts_60s": self.audience.recent(60),
                         "hearts_total": len(self.audience.hearts)},
            "remote": {"code": self.driver_code, "driver": self.driver_active(),
                       "camera": self.camera.ok and self.camera.jpeg is not None,
                       "watch_streams": self.watch_streams, "pan_sign": self.pan_sign},
        }

    def close(self):
        self.camera.close()
        self.body.limp()
        self.head.move(0, 0, 0.4)
        self.face.close()


# ---------------------------------------------------------------- operator page
PAGE = """<!doctype html><html><head><meta name=viewport content="width=device-width,initial-scale=1">
<title>krēCHer operator</title><style>
body{font-family:system-ui,sans-serif;background:#111;color:#eee;margin:0;padding:12px;max-width:520px}
h1{font-size:20px;margin:4px 0 10px} .row{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}
button{flex:1 1 30%;font-size:17px;padding:16px 6px;border:0;border-radius:12px;background:#2a2f3a;color:#fff}
button.beat{background:#1d6b63} button.warn{background:#a8322d} button.on{background:#3a7d2c}
button:active{filter:brightness(1.4)} input{flex:1;font-size:17px;padding:12px;border-radius:10px;border:0}
#st{font:13px/1.5 ui-monospace,monospace;background:#1b1b1b;padding:10px;border-radius:10px;white-space:pre-wrap}
.lbl{font-size:12px;color:#999;margin-top:14px}</style></head><body>
<h1>krēCHer · operator</h1>
<div class=lbl>Demo beats</div>
<div class=row><button class=beat onclick="go('wake')">1 · Wake</button>
<button class=beat onclick="go('hi')">2 · Say hi</button>
<button class=beat onclick="go('feeling')">4 · Feeling?</button></div>
<div class=row><button class=beat onclick="go('goodbye')">12 · Goodbye</button>
<button onclick="go('sleep')">Sleep (quiet)</button></div>
<div class=lbl>Touch reactions</div>
<div class=row><button id=known onclick="go('known')">Known: ?</button>
<button onclick="go('purr')">Purr</button><button onclick="go('flinch')">Flinch</button></div>
<div class=lbl>Audience</div>
<div class=row><button id=hearts onclick="go('hearts')">Hearts: ?</button>
<button onclick="location.href='/tv'">TV screen</button></div>
<div class=lbl>Volunteer (remote driver)</div>
<div class=row><button id=drv style="flex:1 1 100%">Driver code: ?</button></div>
<div class=row><button onclick="go('release')">Take control back</button>
<button onclick="go('newcode')">New code</button><button onclick="go('flip_pan')">Flip drag</button></div>
<div class=row><button onclick="location.href='/view'">Volunteer view (room projector)</button></div>
<div class=lbl>Say something</div>
<div class=row><input id=t placeholder="krēCHer says..."><button style="flex:0 0 80px" onclick="sayit()">Say</button></div>
<div class=lbl>Body and head</div>
<div class=row><button onclick="go('stand')">Stand</button><button onclick="go('crouch')">Crouch</button>
<button onclick="go('center')">Head centre</button><button onclick="go('test_face')">Faces</button></div>
<div class=row><button class=warn onclick="go('limp')">LIMP NOW</button></div>
<div class=lbl>Status</div><div id=st>…</div>
<script>
async function go(a,extra){await fetch('/do',{method:'POST',body:JSON.stringify(Object.assign({a:a},extra||{}))});tick()}
function sayit(){const t=document.getElementById('t');go('say',{text:t.value});t.value=''}
async function tick(){try{const s=await (await fetch('/status')).json();
 const k=document.getElementById('known');k.textContent='Toucher: '+(s.known?'known (purr)':'stranger (flinch)');
 k.className=s.known?'on':'warn';
 const h=document.getElementById('hearts');h.textContent='Hearts '+(s.audience.hearts_on?'ON':'off')+
 ` · ${s.audience.viewers} watching · ${s.audience.hearts_60s}/min`;h.className=s.audience.hearts_on?'on':'';
 const d=document.getElementById('drv');d.textContent=`Driver code: ${s.remote.code} · `+
 (s.remote.driver?'volunteer driving':'nobody driving')+(s.remote.camera?'':' · camera off');d.className=s.remote.driver?'on':'';
 document.getElementById('st').textContent=
 `${s.state}${s.busy?' · busy: '+s.last:''}  face: ${s.face}\\n`+
 `alarm ${s.alarm}  curious ${s.curious}\\n`+
 `distance ${s.dist_in==null?'–':s.dist_in+' in'} · motion/min ${s.motion_60s} · touches/min ${s.touches_60s}\\n`+
 `head battery ${s.battery==null?'–':s.battery+'%'}\\n`+
 `body ${s.body.ok?s.body.pose:'not connected'} · rail ${s.body.rail_v==null?'–':s.body.rail_v+' V'} · ${s.body.fw||''}`;
}catch(e){document.getElementById('st').textContent='no connection'}}
setInterval(tick,1000);tick();
</script></body></html>"""


def send_face(h, k):
    png = k.face.frame_png
    if not png:
        return h._send(404, "no face yet", "text/plain")
    h._send(200, png, "image/png")


def send_still(h, k):
    jpg = k.camera.jpeg
    if not jpg:
        return h._send(503, "camera off", "text/plain")
    h._send(200, jpg, "image/jpeg")


def send_stream(h, k, watcher):
    """Live MJPEG. Watchers are capped; the driver and the TV always get it."""
    if not k.camera.jpeg:
        return h._send(503, "camera off", "text/plain")
    if watcher:
        if k.watch_streams >= MAX_WATCH_STREAMS:
            return h._send(503, "too many viewers", "text/plain")
        k.watch_streams += 1
    try:
        h.send_response(200)
        h.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        h.send_header("Cache-Control", "no-store")
        h.end_headers()
        n = -1
        while True:
            n, jpg = k.camera.wait(n, 3.0)
            if not jpg:
                break
            h.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(jpg))
            h.wfile.write(jpg)
            h.wfile.write(b"\r\n")
    except (BrokenPipeError, ConnectionResetError, OSError):
        pass
    finally:
        if watcher:
            k.watch_streams -= 1


def serve(k, port, public_url=None):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype):
            data = body.encode() if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/":
                self._send(200, PAGE, "text/html; charset=utf-8")
            elif self.path == "/status":
                self._send(200, json.dumps(k.status()), "application/json")
            elif self.path == "/tv":
                self._send(200, TV_PAGE.replace("__URL__", public_url or ""), "text/html; charset=utf-8")
            elif self.path.startswith("/face.png"):
                send_face(self, k)
            elif self.path == "/view":
                self._send(200, VIEW_PAGE, "text/html; charset=utf-8")
            elif self.path.startswith("/cam.mjpg"):
                send_stream(self, k, watcher=False)
            elif self.path.startswith("/cam.jpg"):
                send_still(self, k)
            elif self.path.startswith("/msg"):
                self._send(200, json.dumps({"m": k.last_message}), "application/json")
            else:
                self._send(404, "not found", "text/plain")

        def do_POST(self):
            if self.path != "/do":
                return self._send(404, "not found", "text/plain")
            try:
                n = int(self.headers.get("Content-Length", 0))
                req = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._send(400, "bad json", "text/plain")
            a = req.get("a", "")
            if a == "limp":
                k.emergency_limp()
                ok = True
            elif a == "known":
                k.known = not k.known
                ok = True
            elif a == "hearts":
                k.audience.enabled = not k.audience.enabled
                ok = True
            elif a == "release":
                k.release_driver()
                k.do("center")
                ok = True
            elif a == "newcode":
                k.release_driver(new_code=True)
                ok = True
            elif a == "flip_pan":
                k.pan_sign = -k.pan_sign
                ok = True
            elif a == "say":
                ok = k.do("say", text=str(req.get("text", "")))
            else:
                ok = k.do(a)
            self._send(200 if ok else 400, json.dumps({"ok": ok}), "application/json")

    srv = ThreadingHTTPServer(("0.0.0.0", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


AUDIENCE_PAGE = """<!doctype html><html><head><meta name=viewport content="width=device-width,initial-scale=1">
<title>krēCHer</title><style>
body{font-family:system-ui,sans-serif;background:#0d0f14;color:#eee;margin:0;padding:18px;text-align:center}
h1{font-size:22px;margin:6px 0 2px} .sub{color:#9aa;font-size:14px;margin-bottom:14px}
#face{width:100%;max-width:420px;image-rendering:pixelated;border-radius:14px;border:2px solid #223;background:#000}
#heart{margin:22px auto 10px;width:190px;height:190px;border-radius:50%;border:0;font-size:96px;
 background:radial-gradient(circle,#ff5c93,#c2185b);box-shadow:0 0 40px #ff2d7a88;color:#fff;touch-action:manipulation}
#heart:active{transform:scale(.93)} #heart.off{filter:grayscale(1) brightness(.5)}
#msg{min-height:22px;color:#ffb3cf} #count{color:#9aa;font-size:15px;margin-top:6px}
.float{position:fixed;font-size:34px;pointer-events:none;animation:up 1.4s ease-out forwards}
@keyframes up{to{transform:translateY(-220px) scale(1.6);opacity:0}}</style></head><body>
<h1>krēCHer</h1><div class=sub id=state>…</div>
<img id=cam alt="what krēCHer sees" style="width:100%;max-width:520px;border-radius:14px;background:#000;min-height:120px">
<div style="color:#9aa;font-size:13px;margin:4px 0 12px">what krēCHer sees</div>
<img id=face src="/face.png" alt="krēCHer's face" style="max-width:220px">
<div><button id=heart aria-label="send a heart">❤</button></div>
<div id=msg>Tap the heart to pet krēCHer</div><div id=count></div>
<div style="margin-top:22px"><a href="/driver" style="color:#9cf">I have a driver code</a></div>
<script>
let cid;try{cid=localStorage.getItem('kcid')}catch(e){}
if(!cid){cid=Math.random().toString(36).slice(2,12);try{localStorage.setItem('kcid',cid)}catch(e){}}
const msg=document.getElementById('msg'),btn=document.getElementById('heart');
function floatHeart(){const d=document.createElement('div');d.className='float';d.textContent='❤';
 d.style.left=(40+Math.random()*20)+'%';d.style.top='55%';document.body.appendChild(d);setTimeout(()=>d.remove(),1500)}
btn.onclick=async()=>{floatHeart();try{const r=await (await fetch('/heart',{method:'POST',body:JSON.stringify({id:cid})})).json();
 msg.textContent={ok:'krēCHer felt that ❤',asleep:'krēCHer is asleep. Wait for it to wake up.',off:'Hearts are paused right now.','slow down':'Gently… one heart at a time.'}[r.r]||''}catch(e){msg.textContent='No connection'}};
async function tick(){try{const s=await (await fetch('/state?id='+cid)).json();
 document.getElementById('state').textContent=s.awake?(s.mood):'asleep 💤';
 btn.className=(s.awake&&s.hearts_on)?'':'off';
 document.getElementById('count').textContent=`${s.viewers} here · ❤ ${s.hearts_60s} in the last minute`;
 document.getElementById('face').src='/face.png?'+Date.now()}catch(e){}}
setInterval(tick,700);tick();
const cam=document.getElementById('cam');let still=null;
cam.onerror=()=>{if(still)return;still=setInterval(()=>{cam.src='/cam.jpg?'+Date.now()},2500)};
cam.src='/cam.mjpg?w=1';
</script></body></html>"""

DRIVER_PAGE = """<!doctype html><html><head><meta name=viewport content="width=device-width,initial-scale=1,user-scalable=no">
<title>Drive krēCHer</title><style>
body{font-family:system-ui,sans-serif;background:#0d0f14;color:#eee;margin:0;padding:12px;text-align:center}
h1{font-size:20px;margin:6px 0} input,button{font-size:18px;padding:12px;border-radius:10px;border:0}
button{background:#1d6b63;color:#fff} #code{width:120px;text-align:center;letter-spacing:6px}
#camwrap{position:relative;touch-action:none;user-select:none;-webkit-user-select:none}
#cam{width:100%;border-radius:12px;background:#000;min-height:180px;display:block;pointer-events:none}
#hint{position:absolute;bottom:8px;left:0;right:0;font-size:13px;color:#fffa;text-shadow:0 0 4px #000}
#pet{display:none;background:#c2185b;color:#fff;padding:12px;border-radius:12px;margin:10px 0;font-size:18px}
.row{display:flex;gap:8px;margin:10px 0} .row input{flex:1} #feel{color:#9aa;font-size:14px;line-height:1.6}
#face{width:128px;image-rendering:pixelated;border-radius:8px;vertical-align:middle}</style></head><body>
<div id=login><h1>Drive krēCHer</h1><p>Type the driver code you were given.</p>
<input id=code inputmode=numeric maxlength=4 autocomplete=off> <button onclick="claim()">Go</button>
<p id=lmsg style="color:#ffb3cf"></p></div>
<div id=drive style="display:none">
<div id=camwrap><img id=cam alt="krēCHer's camera"><div id=hint>drag to look around</div></div>
<div id=pet>❤ someone is petting you</div>
<div class=row><input id=say maxlength=120 placeholder="Say something as krēCHer"><button onclick="speak()">Say</button></div>
<div class=row><button style="flex:1;background:#2a2f3a" onclick="center()">Look ahead</button></div>
<div id=feel><img id=face src="/face.png"> <span id=mood></span><br><span id=senses></span></div>
</div>
<script>
let cid;try{cid=localStorage.getItem('kcid')}catch(e){}
if(!cid){cid=Math.random().toString(36).slice(2,12);try{localStorage.setItem('kcid',cid)}catch(e){}}
let pan=0,tilt=0,sign=1,lastTouch=null,driving=false;
async function post(u,o){const r=await fetch(u,{method:'POST',body:JSON.stringify(Object.assign({id:cid},o||{}))});return r.json()}
async function claim(){const r=await post('/claim',{code:document.getElementById('code').value});
 if(r.r==='ok')start();else document.getElementById('lmsg').textContent=
 {'wrong code':'That code is not right.',busy:'Someone else is driving krēCHer right now.'}[r.r]||'Try again.'}
function start(){driving=true;document.getElementById('login').style.display='none';
 document.getElementById('drive').style.display='block';document.getElementById('cam').src='/cam.mjpg';}
const wrap=document.getElementById('camwrap');let drag=null,sendT=0;
wrap.addEventListener('pointerdown',e=>{drag={x:e.clientX,y:e.clientY,p:pan,t:tilt};wrap.setPointerCapture(e.pointerId)});
wrap.addEventListener('pointermove',e=>{if(!drag)return;const w=wrap.clientWidth;
 pan=Math.max(-45,Math.min(45,drag.p+sign*(e.clientX-drag.x)/w*-70));
 tilt=Math.max(-15,Math.min(12,drag.t+(e.clientY-drag.y)/w*40));
 const now=Date.now();if(now-sendT>90){sendT=now;post('/look',{pan:pan,tilt:tilt})}});
wrap.addEventListener('pointerup',e=>{if(drag){post('/look',{pan:pan,tilt:tilt})}drag=null});
function center(){pan=0;tilt=0;post('/look',{pan:0,tilt:0})}
async function speak(){const t=document.getElementById('say');if(!t.value.trim())return;
 await post('/speak',{text:t.value});t.value=''}
document.getElementById('say').addEventListener('keydown',e=>{if(e.key==='Enter')speak()});
async function tick(){try{const s=await (await fetch('/state?id='+cid)).json();
 if(s.driver&&!driving){pan=s.pan;tilt=s.tilt;start()}
 if(driving&&!s.driver){driving=false;document.getElementById('drive').style.display='none';
  document.getElementById('login').style.display='block';
  document.getElementById('lmsg').textContent='Thank you for driving krēCHer!'}
 sign=s.pan_sign||1;
 document.getElementById('mood').textContent=s.awake?('krēCHer feels '+s.mood):'krēCHer is asleep';
 document.getElementById('senses').textContent=(s.dist_in==null?'nothing close':'nearest thing '+s.dist_in+' in away')+
  (s.motion?' · someone moving nearby':'');
 document.getElementById('face').src='/face.png?'+Date.now();
 if(lastTouch!==null&&s.touches>lastTouch){const p=document.getElementById('pet');p.style.display='block';
  try{navigator.vibrate&&navigator.vibrate([80,60,80])}catch(e){}setTimeout(()=>p.style.display='none',2500)}
 lastTouch=s.touches}catch(e){}}
setInterval(tick,600);tick();
</script></body></html>"""

VIEW_PAGE = """<!doctype html><html><head><title>krēCHer · volunteer view</title><style>
body{margin:0;background:#000;height:100vh;overflow:hidden;font-family:system-ui,sans-serif}
#cam{width:100vw;height:100vh;object-fit:contain} #face{position:fixed;right:2vw;bottom:2vw;width:18vw;
 image-rendering:pixelated;border:2px solid #333;border-radius:1vw}
#msg{position:fixed;left:0;right:0;top:3vh;text-align:center;color:#fff;font-size:4vw;text-shadow:0 0 8px #000}
</style></head><body><img id=cam src="/cam.mjpg"><img id=face src="/face.png"><div id=msg></div>
<script>setInterval(async()=>{document.getElementById('face').src='/face.png?'+Date.now();
try{const m=await (await fetch('/msg')).json();document.getElementById('msg').textContent=m.m||''}catch(e){}},700);
</script></body></html>"""

TV_PAGE = """<!doctype html><html><head><title>krēCHer · TV</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script><style>
body{margin:0;background:#07080c;color:#eee;font-family:system-ui,sans-serif;height:100vh;display:flex;
 align-items:center;justify-content:space-around}
#face{width:46vw;image-rendering:pixelated;border-radius:2vw;border:3px solid #1c2233}
.side{text-align:center} #qr{background:#fff;padding:1.4vw;border-radius:1.4vw;display:inline-block}
.big{font-size:3vw;margin-top:1.4vw} .url{font-size:1.4vw;color:#9aa;margin-top:.6vw}
#hearts{font-size:4.5vw;color:#ff5c93;margin-top:2vw} #pulse{transition:transform .2s}</style></head><body>
<div style="position:relative"><img id=cam src="/cam.mjpg" style="width:52vw;border-radius:2vw;background:#000">
<img id=face src="/face.png" style="position:absolute;right:1vw;bottom:1vw;width:16vw;border-width:2px"></div>
<div class=side><div id=qr></div><div class=big>Scan to pet krēCHer</div><div class=url id=url></div>
<div id=hearts><span id=pulse>❤</span> <span id=n>0</span></div><div class=url id=w></div></div>
<script>
const url="__URL__";document.getElementById('url').textContent=url||'(Funnel URL not found: start demo.py with --public-url)';
try{if(url)new QRCode(document.getElementById('qr'),{text:url,width:300,height:300})}catch(e){}
let last=0;
async function tick(){try{const s=await (await fetch('/status')).json();
 document.getElementById('n').textContent=s.audience.hearts_60s+' / min';
 document.getElementById('w').textContent=s.audience.viewers+' people connected';
 if(s.audience.hearts_total>last){const p=document.getElementById('pulse');p.style.transform='scale(1.5)';
  setTimeout(()=>p.style.transform='',200)}last=s.audience.hearts_total;
 document.getElementById('face').src='/face.png?'+Date.now()}catch(e){}}
setInterval(tick,500);tick();
</script></body></html>"""


def serve_audience(k, port):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype):
            data = body.encode() if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path, _, query = self.path.partition("?")
            if path == "/":
                self._send(200, AUDIENCE_PAGE, "text/html; charset=utf-8")
            elif path == "/face.png":
                send_face(self, k)
            elif path == "/driver":
                self._send(200, DRIVER_PAGE, "text/html; charset=utf-8")
            elif path == "/cam.mjpg":
                send_stream(self, k, watcher=not k.is_driver(self._cid_cookie(query)))
            elif path == "/cam.jpg":
                send_still(self, k)
            elif path == "/state":
                cid = query[3:] if query.startswith("id=") else ""
                k.audience.poll(cid)
                k.driver_seen(cid)
                mood = {"calm": "calm", "curious": "curious", "cautious": "a little nervous",
                        "purr": "purring", "love": "feeling loved", "flinch": "startled!",
                        "awake": "awake", "shy": "shy"}.get(k.face.expr, k.face.expr)
                self._send(200, json.dumps({
                    "awake": k.state == "awake", "mood": mood, "hearts_on": k.audience.enabled,
                    "viewers": k.audience.viewers(), "hearts_60s": k.audience.recent(60),
                    "driver": k.is_driver(cid), "pan": k.head.p, "tilt": k.head.t,
                    "pan_sign": k.pan_sign, "touches": k.touch_count,
                    "dist_in": None if k.senses.dist is None else round(k.senses.dist / 2.54),
                    "motion": k.senses.recent(k.senses.motion, 10) > 0}),
                    "application/json")
            else:
                self._send(404, "not found", "text/plain")

        def _cid_cookie(self, query):
            """The driver page's stream request carries no id; match by the last driver poll instead."""
            return k.driver["id"] if (k.driver_active() and "w=1" not in query) else ""

        def do_POST(self):
            try:
                n = min(int(self.headers.get("Content-Length", 0)), 1000)
                req = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                req = {}
            cid = str(req.get("id", ""))[:40]
            if self.path == "/heart":
                r = k.audience.heart(cid)
            elif self.path == "/claim":
                r = k.claim(cid, req.get("code", ""))
            elif self.path == "/look":
                try:
                    r = "ok" if k.look(cid, req.get("pan", 0), req.get("tilt", 0)) else "not driver"
                except (TypeError, ValueError):
                    r = "error"
            elif self.path == "/speak":
                if k.is_driver(cid):
                    k.do("remote_say", text=str(req.get("text", "")))
                    r = "ok"
                else:
                    r = "not driver"
            else:
                return self._send(404, "not found", "text/plain")
            self._send(200, json.dumps({"r": r}), "application/json")

    srv = ThreadingHTTPServer(("0.0.0.0", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def find_public_url():
    """The Funnel address, from Tailscale: https://<machine>.<tailnet>.ts.net/"""
    try:
        out = subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True, timeout=5)
        name = json.loads(out.stdout)["Self"]["DNSName"].rstrip(".")
        return "https://%s/" % name if name else None
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-body", action="store_true", help="don't use the legs")
    ap.add_argument("--no-camera", action="store_true", help="don't start the camera")
    ap.add_argument("--cam-rotation", type=int, default=0, choices=(0, 180), help="180 if the picture is upside down")
    ap.add_argument("--port", type=int, default=OPERATOR_PORT)
    ap.add_argument("--audience-port", type=int, default=AUDIENCE_PORT)
    ap.add_argument("--public-url", help="the audience link for the QR code (default: the Funnel address)")
    args = ap.parse_args()
    k = Krecher(use_body=not args.no_body, use_camera=not args.no_camera, cam_rotation=args.cam_rotation)
    public_url = args.public_url or find_public_url()
    serve(k, args.port, public_url)
    serve_audience(k, args.audience_port)
    log("operator page: http://100.75.140.37:%d   TV: http://100.75.140.37:%d/tv  (Tailscale)"
        % (args.port, args.port))
    log("audience page: %s  (needs: sudo tailscale funnel --bg %d)  ·  Ctrl+C to stop"
        % (public_url or "http://100.75.140.37:%d" % args.audience_port, args.audience_port))
    log("volunteer: %sdriver   driver code: %s (also on the operator page)"
        % (public_url or "http://100.75.140.37:%d/" % args.audience_port, k.driver_code))
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log("stopping")
    finally:
        k.close()


if __name__ == "__main__":
    main()
