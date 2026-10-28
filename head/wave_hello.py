"""krēCHer stands, waves its front-left leg and says hello.

Run on the Pi, from the IMU/head venv:
    source ~/venvs/imu/bin/activate
    python ~/krecher/head/wave_hello.py

Starts body/stand_wave.py on the Servo 2040, waits for "waving", then speaks
while the leg waves. Ctrl+C: all 18 leg servos go limp and the head re-centres.
"""
import os, shutil, subprocess, sys, time
from fusion_hat.servo import Servo

GREETING = "Hello! I'm krecher."
MPREMOTE = os.path.expanduser("~/venvs/servo/bin/mpremote")
BODY = os.path.expanduser("~/krecher/body/stand_wave.py")
PORT = "/dev/ttyACM0"

pan, tilt = Servo(2), Servo(3)
head = {"pan": 0, "tilt": 0}

def move(p, t, secs=1.0):
    steps = max(1, int(secs / 0.03))
    p0, t0 = head["pan"], head["tilt"]
    for i in range(1, steps + 1):
        f = i / steps
        f = f * f * (3 - 2 * f)
        pan.angle(round(p0 + (p - p0) * f, 1))
        tilt.angle(round(t0 + (t - t0) * f, 1))
        time.sleep(0.03)
    head["pan"], head["tilt"] = p, t

def say(text):
    try:
        from fusion_hat.utils import enable_speaker
        enable_speaker()
    except Exception:
        pass
    if shutil.which("pico2wave") and shutil.which("aplay"):
        wav = "/tmp/krecher_say.wav"
        subprocess.run(["pico2wave", "-l", "en-US", "-w", wav, text], check=False)
        subprocess.run(["aplay", "-q", wav], check=False)
    elif shutil.which("espeak-ng") or shutil.which("espeak"):
        cmd = shutil.which("espeak-ng") or shutil.which("espeak")
        subprocess.run([cmd, "-s", "140", "-p", "60", text], check=False)
    else:
        print("(no voice installed: sudo apt install espeak-ng)  SAY:", text)

body = None
try:
    move(0, 0, 0.3)
    if not os.path.exists(PORT):
        sys.exit("Servo 2040 not found at %s: plug its USB cable into the Pi." % PORT)
    print("starting the body...")
    body = subprocess.Popen([MPREMOTE, "connect", PORT, "run", BODY],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    for line in body.stdout:
        print("  body:", line.rstrip())
        if "waving" in line:
            break
    else:
        sys.exit("The body script ended before waving (see the lines above).")

    move(0, 12, 0.5)          # look up at the person
    say(GREETING)
    move(0, 0, 0.8)
    for line in body.stdout:
        print("  body:", line.rstrip())
    body.wait()
except KeyboardInterrupt:
    print("\nstopping")
finally:
    if body and body.poll() is None:
        body.terminate()
        try:
            body.wait(timeout=3)
        except subprocess.TimeoutExpired:
            body.kill()
        subprocess.run([MPREMOTE, "connect", PORT, "exec",
                        "from servo import Servo, servo2040\n"
                        "for c in range(servo2040.NUM_SERVOS): Servo(servo2040.SERVO_1 + c).disable()"],
                       check=False)
    move(0, 0, 0.5)
