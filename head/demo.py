"""krēCHer's demo program (core, Nov 5): wake, say hi, purr / flinch, how are you feeling,
goodbye, all driven from an operator page on your phone.

Run on the Pi, from the IMU/head venv:
    source ~/venvs/imu/bin/activate
    python ~/krecher/head/demo.py              # everything
    python ~/krecher/head/demo.py --no-body    # head, face and sensors only (LiPo out, no legs)

Then open the operator page on your phone or Mac (Tailscale on):
    http://100.75.140.37:8001        operator buttons
    http://100.75.140.37:8001/tv     the TV screen: QR code, face, hearts

The audience page (hearts) is on port 8000. To reach it from anyone's phone, turn Funnel on
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
    def __init__(self, use_body=True):
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
        try:
            from fusion_hat.device import enable_speaker
            enable_speaker()
        except Exception:
            pass
        make_purr()
        self.senses = Senses(self._on_touch, self._on_motion)
        threading.Thread(target=self._worker, daemon=True).start()
        threading.Thread(target=self._mood_loop, daemon=True).start()

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

    # ---- reflexes ---------------------------------------------------------------
    def _on_touch(self):
        log("touch", "(known)" if self.known else "(stranger)")
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
        }

    def close(self):
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
<img id=face src="/face.png" alt="krēCHer's face">
<div><button id=heart aria-label="send a heart">❤</button></div>
<div id=msg>Tap the heart to pet krēCHer</div><div id=count></div>
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
</script></body></html>"""

TV_PAGE = """<!doctype html><html><head><title>krēCHer · TV</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script><style>
body{margin:0;background:#07080c;color:#eee;font-family:system-ui,sans-serif;height:100vh;display:flex;
 align-items:center;justify-content:space-around}
#face{width:46vw;image-rendering:pixelated;border-radius:2vw;border:3px solid #1c2233}
.side{text-align:center} #qr{background:#fff;padding:1.4vw;border-radius:1.4vw;display:inline-block}
.big{font-size:3vw;margin-top:1.4vw} .url{font-size:1.4vw;color:#9aa;margin-top:.6vw}
#hearts{font-size:4.5vw;color:#ff5c93;margin-top:2vw} #pulse{transition:transform .2s}</style></head><body>
<img id=face src="/face.png">
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
            elif path == "/state":
                cid = query[3:] if query.startswith("id=") else ""
                k.audience.poll(cid)
                mood = {"calm": "calm", "curious": "curious", "cautious": "a little nervous",
                        "purr": "purring", "love": "feeling loved", "flinch": "startled!",
                        "awake": "awake", "shy": "shy"}.get(k.face.expr, k.face.expr)
                self._send(200, json.dumps({
                    "awake": k.state == "awake", "mood": mood, "hearts_on": k.audience.enabled,
                    "viewers": k.audience.viewers(), "hearts_60s": k.audience.recent(60)}),
                    "application/json")
            else:
                self._send(404, "not found", "text/plain")

        def do_POST(self):
            if self.path != "/heart":
                return self._send(404, "not found", "text/plain")
            try:
                n = min(int(self.headers.get("Content-Length", 0)), 500)
                req = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                req = {}
            r = k.audience.heart(str(req.get("id", "")))
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
    ap.add_argument("--port", type=int, default=OPERATOR_PORT)
    ap.add_argument("--audience-port", type=int, default=AUDIENCE_PORT)
    ap.add_argument("--public-url", help="the audience link for the QR code (default: the Funnel address)")
    args = ap.parse_args()
    k = Krecher(use_body=not args.no_body)
    public_url = args.public_url or find_public_url()
    serve(k, args.port, public_url)
    serve_audience(k, args.audience_port)
    log("operator page: http://100.75.140.37:%d   TV: http://100.75.140.37:%d/tv  (Tailscale)"
        % (args.port, args.port))
    log("audience page: %s  (needs: sudo tailscale funnel --bg %d)  ·  Ctrl+C to stop"
        % (public_url or "http://100.75.140.37:%d" % args.audience_port, args.audience_port))
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log("stopping")
    finally:
        k.close()


if __name__ == "__main__":
    main()
