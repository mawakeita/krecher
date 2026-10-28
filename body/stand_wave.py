# stand_wave.py: stand up (same as stand_up.py), lift the front-left leg and wave it,
# put it back down, hold, sit, limp. Prints "waving" when the wave starts;
# head/wave_hello.py waits for that line to say hello.
# Safety: run on the box as usual, so if the body tips toward the lifted leg the box catches it.
import time
from servo import Servo, servo2040

FEMUR_DOWN = {"L": -1, "R": 1}   # from dir_test.py, Oct 8
KNEE_OUT   = {"L": -1, "R": 1}
LEGS = {"FL": ("L", 1), "ML": ("L", 4), "RL": ("L", 7),
        "FR": ("R", 10), "MR": ("R", 13), "RR": ("R", 16)}

CROUCH = -25
STAND  = 10
STEP_S = 0.08

WAVE_LEG   = "FL"   # front left (walking direction = front)
LIFT       = -35    # femur angle in pose units: negative = knee end up (about 45 deg above standing)
REACH      = -30    # knee angle in pose units: negative = foot out, so the raised leg reaches forward
WAVE_HIP   = 20     # hip swings +/- this many degrees
WAVES      = 3
HOLD_AFTER = 4      # seconds standing on all six after the wave

legs = {}
for name, (side, ch) in LEGS.items():
    legs[name] = (side,
                  Servo(servo2040.SERVO_1 + ch - 1),   # hip
                  Servo(servo2040.SERVO_1 + ch),       # femur
                  Servo(servo2040.SERVO_1 + ch + 1))   # knee

def pose(theta):
    for side, hip, fem, knee in legs.values():
        fem.value(FEMUR_DOWN[side] * theta)
        knee.value(KNEE_OUT[side] * theta)

def ramp(a, b):
    step = 1 if b > a else -1
    for t in range(a, b + step, step):
        pose(t)
        time.sleep(STEP_S)

def glide(moves, secs):
    """moves: list of (servo, start, end) values; move them together, eased, over secs."""
    n = max(1, int(secs / 0.02))
    for i in range(1, n + 1):
        f = i / n
        f = f * f * (3 - 2 * f)
        for s, a, b in moves:
            s.value(a + (b - a) * f)
        time.sleep(0.02)

side, hip, fem, knee = legs[WAVE_LEG]
fem_stand, knee_stand = FEMUR_DOWN[side] * STAND, KNEE_OUT[side] * STAND
fem_up, knee_up = FEMUR_DOWN[side] * LIFT, KNEE_OUT[side] * REACH

try:
    print("crouch: lifting the feet, one servo at a time")
    for s, h, f, k in legs.values():
        h.value(0);                        time.sleep(0.15)
        f.value(FEMUR_DOWN[s] * CROUCH);   time.sleep(0.15)
        k.value(KNEE_OUT[s] * CROUCH);     time.sleep(0.15)
    time.sleep(2)
    print("standing up...")
    ramp(CROUCH, STAND)
    time.sleep(1.5)

    print("waving")
    glide([(fem, fem_stand, fem_up), (knee, knee_stand, knee_up)], 1.2)   # raise the leg
    h = 0
    for _ in range(WAVES):
        glide([(hip, h, WAVE_HIP)], 0.4);  h = WAVE_HIP
        glide([(hip, h, -WAVE_HIP)], 0.5); h = -WAVE_HIP
    glide([(hip, h, 0)], 0.3)
    time.sleep(0.3)
    glide([(fem, fem_up, fem_stand), (knee, knee_up, knee_stand)], 1.5)   # put it down gently
    print("leg down - holding", HOLD_AFTER, "s")
    time.sleep(HOLD_AFTER)

    print("sitting down...")
    ramp(STAND, CROUCH)
    time.sleep(2)
finally:
    for _, h_, f_, k_ in legs.values():
        h_.disable(); f_.disable(); k_.disable()
    print("done, all limp")
