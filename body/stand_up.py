import time
from servo import Servo, servo2040

# Directions found Oct 8 with dir_test.py:
#   left femur + = knee end up,   left knee + = foot in
#   right femur + = knee end down, right knee + = foot out
FEMUR_DOWN = {"L": -1, "R": 1}
KNEE_OUT   = {"L": -1, "R": 1}
LEGS = {"FL": ("L", 1), "ML": ("L", 4), "RL": ("L", 7),
        "FR": ("R", 10), "MR": ("R", 13), "RR": ("R", 16)}

CROUCH = -25   # femurs 25 deg up: feet lifted, body resting on the boxes
STAND  = 10    # femurs 10 deg down past level: body raised
STEP_S = 0.08  # seconds per 1-degree step (about 3 s from crouch to stand)

legs = []
for name, (side, ch) in LEGS.items():
    hip  = Servo(servo2040.SERVO_1 + ch - 1)
    fem  = Servo(servo2040.SERVO_1 + ch)
    knee = Servo(servo2040.SERVO_1 + ch + 1)
    legs.append((side, hip, fem, knee))

def pose(theta):
    # theta > 0 pushes the feet down; the knee turns the opposite way so the calf stays upright
    for side, hip, fem, knee in legs:
        fem.value(FEMUR_DOWN[side] * theta)
        knee.value(KNEE_OUT[side] * theta)

def ramp(a, b):
    step = 1 if b > a else -1
    for t in range(a, b + step, step):
        pose(t)
        time.sleep(STEP_S)

try:
    print("crouch: lifting the feet, one servo at a time")
    for side, hip, fem, knee in legs:
        hip.value(0);                        time.sleep(0.15)
        fem.value(FEMUR_DOWN[side] * CROUCH); time.sleep(0.15)
        knee.value(KNEE_OUT[side] * CROUCH);  time.sleep(0.15)
    time.sleep(2)
    print("standing up...")
    ramp(CROUCH, STAND)
    print("standing - holding 30 s")
    time.sleep(30)
    print("sitting down...")
    ramp(STAND, CROUCH)
    time.sleep(2)
finally:
    for _, hip, fem, knee in legs:
        hip.disable(); fem.disable(); knee.disable()
    print("done, all limp")
