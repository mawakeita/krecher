"""krēCHer says hello: stand up, greet, look around, sit down.

Run on the Pi, from the IMU/head venv (it can see fusion_hat):
    source ~/venvs/imu/bin/activate
    python ~/krecher/head/hello.py

It starts body/stand_hello.py on the Servo 2040 (via mpremote), waits until the
body reports it is holding, then speaks and sweeps the camera head. The body sits
down and goes limp by itself when its hold ends. Ctrl+C stops everything: the body
goes limp and the head re-centres.
"""
import os, shutil, subprocess, sys, time
from fusion_hat.servo import Servo

GREETING = "Hello! I'm krecher."     # spelled for the voice; the name is krēCHer
MPREMOTE = os.path.expanduser("~/venvs/servo/bin/mpremote")
BODY = os.path.expanduser("~/krecher/body/stand_hello.py")
PORT = "/dev/ttyACM0"

pan, tilt = Servo(2), Servo(3)     # PWM 2 = pan, PWM 3 = tilt
head = {"pan": 0, "tilt": 0}

def move(p, t, secs=1.0):
    """Glide the head to (pan p, tilt t) degrees over about secs seconds."""
    steps = max(1, int(secs / 0.03))
    p0, t0 = head["pan"], head["tilt"]
    for i in range(1, steps + 1):
        f = i / steps
        f = f * f * (3 - 2 * f)                       # ease in and out
        pan.angle(round(p0 + (p - p0) * f, 1))
        tilt.angle(round(t0 + (t - t0) * f, 1))
        time.sleep(0.03)
    head["pan"], head["tilt"] = p, t

def say(text):
    """Speak with whichever voice is installed; print if there is none."""
    try:
        from fusion_hat.utils import enable_speaker   # switches the HAT's amp on, if this version has it
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

def look_around():
    move(0, 10, 0.6)          # look up at whoever is there
    time.sleep(0.4)
    move(-45, 5, 1.5)         # look to one side
    time.sleep(0.6)
    move(45, 5, 2.2)          # across to the other side
    time.sleep(0.6)
    move(20, -15, 1.0)        # glance down at the floor
    time.sleep(0.5)
    move(0, 0, 1.0)           # back to centre

body = None
try:
    move(0, 0, 0.3)
    if not os.path.exists(PORT):
        sys.exit("Servo 2040 not found at %s: plug its USB cable into the Pi." % PORT)
    print("starting the body...")
    body = subprocess.Popen([MPREMOTE, "connect", PORT, "run", BODY],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    for line in body.stdout:                     # wait until the body is up
        print("  body:", line.rstrip())
        if "holding" in line:
            break
    else:
        sys.exit("The body script ended before standing (see the lines above).")

    time.sleep(0.5)
    say(GREETING)
    look_around()
    print("done greeting; the body sits down when its hold ends")
    for line in body.stdout:                     # show the rest: sitting down, limp
        print("  body:", line.rstrip())
    body.wait()
except KeyboardInterrupt:
    print("\nstopping")
finally:
    if body and body.poll() is None:
        body.terminate()                         # interrupting mpremote stops the body script...
        try:
            body.wait(timeout=3)
        except subprocess.TimeoutExpired:
            body.kill()
        # ...and the board's try/finally may not run if mpremote is killed, so go limp explicitly
        subprocess.run([MPREMOTE, "connect", PORT, "exec",
                        "from servo import Servo, servo2040\n"
                        "for c in range(servo2040.NUM_SERVOS): Servo(servo2040.SERVO_1 + c).disable()"],
                       check=False)
    move(0, 0, 0.5)
