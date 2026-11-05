"""krēCHer's face (OLED eyes + mouth) and mood glow (RGB ring in the basket).

A building block for head/demo.py. On its own it is a quiet test: no body
movement, no camera, so it can run while the projector is busy.

Run on the Pi, from the IMU/head venv:
    source ~/venvs/imu/bin/activate
    python ~/krecher/head/face.py            # every expression, 4 s each
    python ~/krecher/head/face.py purr       # just one (Ctrl+C to stop)
    python ~/krecher/head/face.py --talk     # says a line with the mouth moving

Hardware (as wired Oct 17): OLED 128x64 SSD1306 on the HAT's I2C header (0x3C),
12 x WS2812 ring on the SPI header MO, GRB, brightness 0.2. Libraries already in
~/venvs/imu: adafruit-circuitpython-ssd1306, pillow, adafruit-circuitpython-neopixel-spi.
If one part is missing, the other still runs and a warning is printed.

Use from other code:
    from face import Face
    face = Face()
    face.set("calm")              # see EXPRESSIONS
    face.look(-0.5, 0)            # eyes glance left (-1..1, -1..1)
    face.talking(True)            # mouth moves until talking(False)
    face.close()
"""
import math, re, shutil, subprocess, sys, threading, time

W, H = 128, 64

# name: eyes shape, mouth shape, ring colour (R, G, B), ring style
EXPRESSIONS = {
    "sleep":    dict(eyes="closed", mouth="none",  ring=(0, 120, 110),  glow="breathe_slow"),
    "awake":    dict(eyes="round",  mouth="smile", ring=(0, 200, 180),  glow="steady"),
    "calm":     dict(eyes="round",  mouth="smile", ring=(0, 200, 180),  glow="breathe"),
    "purr":     dict(eyes="happy",  mouth="wave",  ring=(0, 220, 160),  glow="purr"),
    "curious":  dict(eyes="big",    mouth="small", ring=(255, 170, 0),  glow="steady"),
    "cautious": dict(eyes="narrow", mouth="flat",  ring=(255, 120, 0),  glow="breathe"),
    "flinch":   dict(eyes="wide",   mouth="o",     ring=(255, 0, 0),    glow="flash"),
    "shy":      dict(eyes="down",   mouth="small", ring=(255, 90, 120), glow="steady"),
    "love":     dict(eyes="happy",  mouth="smile", ring=(255, 40, 120), glow="pulse"),
}


class Face:
    def __init__(self, brightness=0.2, fps=12):
        self.oled = self.ring = None
        self._lock = threading.Lock()
        self.expr = "sleep"
        self.gaze = (0.0, 0.0)
        self._talk = False
        self._pulse_at = 0.0           # time of the last one-off ring pulse (hearts)
        self._since = time.monotonic()
        self._fps = fps
        self._Image = None
        self.frame_png = None          # the current face as a PNG (for the audience and TV pages)
        try:
            from PIL import Image, ImageDraw
            self._Image, self._Draw = Image, ImageDraw
        except Exception as e:
            print("face: pillow not available (%s)" % e)
        try:
            import board, adafruit_ssd1306
            self.oled = adafruit_ssd1306.SSD1306_I2C(W, H, board.I2C(), addr=0x3C)
        except Exception as e:
            print("face: OLED not available (%s)" % e)
        try:
            import board, neopixel_spi
            self.ring = neopixel_spi.NeoPixel_SPI(board.SPI(), 12, pixel_order=neopixel_spi.GRB,
                                                  auto_write=False, brightness=brightness)
        except Exception as e:
            print("face: RGB ring not available (%s)" % e)
        self._last_frame = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    # ---- public -------------------------------------------------------
    def set(self, name):
        if name not in EXPRESSIONS:
            raise ValueError("unknown expression %r (have: %s)" % (name, ", ".join(EXPRESSIONS)))
        with self._lock:
            if name != self.expr:
                self.expr, self._since = name, time.monotonic()

    def look(self, x, y=0.0):
        """Eyes glance: x -1 (left) .. 1 (right), y -1 (down) .. 1 (up)."""
        with self._lock:
            self.gaze = (max(-1, min(1, x)), max(-1, min(1, y)))

    def talking(self, on):
        with self._lock:
            self._talk = bool(on)

    def pulse(self):
        """One soft flash of the ring, e.g. for each heart from the audience."""
        with self._lock:
            self._pulse_at = time.monotonic()

    def close(self):
        self._stop.set()
        self._thread.join(timeout=1)
        if self.ring:
            self.ring.fill((0, 0, 0)); self.ring.show()
        if self.oled:
            self.oled.fill(0); self.oled.show()

    # ---- drawing ------------------------------------------------------
    def _run(self):
        while not self._stop.is_set():
            with self._lock:
                expr, gaze, talk = self.expr, self.gaze, self._talk
                age, pulse_age = time.monotonic() - self._since, time.monotonic() - self._pulse_at
            t = time.monotonic()
            try:
                if self._Image:
                    self._draw_oled(EXPRESSIONS[expr], gaze, talk, t)
                if self.ring:
                    self._draw_ring(EXPRESSIONS[expr], age, pulse_age, t)
            except OSError as e:          # a glitch on the shared I2C bus: skip a frame
                print("face: draw error (%s)" % e)
            time.sleep(1.0 / self._fps)

    def _draw_oled(self, ex, gaze, talk, t):
        img = self._Image.new("1", (W, H))
        d = self._Draw.Draw(img)
        blink = ex["eyes"] in ("round", "big", "narrow") and (t % 4.0) < 0.15   # blink every 4 s
        gx, gy = int(gaze[0] * 8), int(-gaze[1] * 5)
        for cx in (38, 90):                                   # eye centres
            x, y = cx + gx, 24 + gy
            e = "closed" if blink else ex["eyes"]
            if e == "closed":
                d.line((x - 12, y + 2, x + 12, y + 2), fill=1, width=3)
            elif e == "round":
                d.ellipse((x - 10, y - 12, x + 10, y + 12), fill=1)
            elif e == "big":
                d.ellipse((x - 13, y - 15, x + 13, y + 15), fill=1)
                d.ellipse((x - 4, y - 9, x + 3, y - 2), fill=0)          # sparkle
            elif e == "wide":
                d.ellipse((x - 15, y - 16, x + 15, y + 16), outline=1, width=3)
                d.ellipse((x - 4, y - 4, x + 4, y + 4), fill=1)          # tiny pupil
            elif e == "narrow":
                d.ellipse((x - 11, y - 5, x + 11, y + 5), fill=1)
            elif e == "happy":                                          # ^ ^ arcs
                d.arc((x - 12, y - 6, x + 12, y + 14), 200, 340, fill=1, width=3)
            elif e == "down":
                d.ellipse((x - 9, y - 2, x + 9, y + 14), fill=1)
                d.rectangle((x - 10, y - 3, x + 10, y + 4), fill=0)      # heavy lids
        m = ex["mouth"]
        mx, my = 64 + gx // 2, 52
        if talk:                                               # open-close while speaking
            h = 2 + int(5 * abs(math.sin(t * 9)))
            d.ellipse((mx - 8, my - h, mx + 8, my + h), fill=1)
        elif m == "smile":
            d.arc((mx - 10, my - 10, mx + 10, my + 4), 20, 160, fill=1, width=2)
        elif m == "small":
            d.arc((mx - 5, my - 6, mx + 5, my + 2), 20, 160, fill=1, width=2)
        elif m == "flat":
            d.line((mx - 8, my, mx + 8, my), fill=1, width=2)
        elif m == "o":
            d.ellipse((mx - 6, my - 7, mx + 6, my + 7), outline=1, width=2)
        elif m == "wave":                                      # purring ~~~
            pts = [(mx - 14 + i, my + int(2.5 * math.sin(i / 2.2 + t * 6))) for i in range(29)]
            d.line(pts, fill=1, width=2)
        frame = img.tobytes()
        if frame != self._last_frame:                          # only send changed frames
            if self.oled:
                self.oled.image(img); self.oled.show()
            self._last_frame = frame
            import io
            buf = io.BytesIO()
            img.convert("L").resize((W * 4, H * 4), self._Image.NEAREST).save(buf, "PNG")
            self.frame_png = buf.getvalue()

    def _draw_ring(self, ex, age, pulse_age, t):
        r, g, b = ex["ring"]
        style = ex["glow"]
        if style == "steady":
            k = 1.0
        elif style == "breathe":
            k = 0.55 + 0.45 * math.sin(t * 1.6)
        elif style == "breathe_slow":
            k = 0.15 + 0.35 * (0.5 + 0.5 * math.sin(t * 0.9))
        elif style == "purr":
            k = 0.7 + 0.3 * math.sin(t * 25)                    # fast flutter
        elif style == "pulse":
            k = 0.5 + 0.5 * abs(math.sin(t * 3))
        elif style == "flash":
            k = 1.0 if (age < 1.2 and int(age * 8) % 2 == 0) else 0.6
        else:
            k = 1.0
        if pulse_age < 0.4:                                    # one-off heart pulse, in pink
            f = 1 - pulse_age / 0.4
            r, g, b = (int(r + (255 - r) * f), int(g + (40 - g) * f), int(b + (120 - b) * f))
            k = max(k, f)
        self.ring.fill((int(r * k), int(g * k), int(b * k)))
        self.ring.show()


def spoken(text):
    """Spell words the way the voice should say them: krēCHer sounds like "creature"."""
    return re.sub(r"kr[eē]ch[eē]r", "creature", text, flags=re.IGNORECASE)


def say(text, face=None):
    """Speak (same voices as hello.py) with the mouth moving."""
    text = spoken(text)
    try:
        from fusion_hat.device import enable_speaker
        enable_speaker()
    except Exception:
        pass
    if face:
        face.talking(True)
    try:
        if shutil.which("pico2wave") and shutil.which("aplay"):
            wav = "/tmp/krecher_say.wav"
            subprocess.run(["pico2wave", "-l", "en-US", "-w", wav, text], check=False)
            subprocess.run(["aplay", "-q", wav], check=False)
        elif shutil.which("espeak-ng") or shutil.which("espeak"):
            cmd = shutil.which("espeak-ng") or shutil.which("espeak")
            subprocess.run([cmd, "-s", "140", "-p", "60", text], check=False)
        else:
            print("SAY:", text); time.sleep(2)
    finally:
        if face:
            face.talking(False)


if __name__ == "__main__":
    args = sys.argv[1:]
    face = Face()
    try:
        if "--talk" in args:
            face.set("awake")
            time.sleep(1)
            say("Hello! I'm krecher. This is my face.", face)
            time.sleep(1)
        elif args:
            face.set(args[0])
            print("showing %s (Ctrl+C to stop)" % args[0])
            while True:
                time.sleep(1)
        else:
            for name in EXPRESSIONS:
                print(name)
                face.set(name)
                if name == "cautious":                 # glance side to side
                    for x in (-1, 1, 0):
                        face.look(x); time.sleep(1.3)
                    face.look(0)
                elif name == "love":                   # three heart pulses
                    for _ in range(3):
                        face.pulse(); time.sleep(1.3)
                else:
                    time.sleep(4)
    except KeyboardInterrupt:
        pass
    finally:
        face.close()
