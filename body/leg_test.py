import time
from servo import Servo, servo2040

# hip, femur, knee channels. FL = 1,2,3
LEGS = {
    "FL": [1, 2, 3],
    "ML": [4, 5, 6],
    "RL": [7, 8, 9],
    "FR": [10, 11, 12],
    "MR": [13, 14, 15],
    "RR": [16, 17, 18],
}
LEG = LEGS["ML"]   # change this word for each leg
servos = [Servo(servo2040.SERVO_1 + n - 1) for n in LEG]

for s in servos:
    s.value(0)          # middle position
time.sleep(5)

for s in servos:        # small wiggle, one joint at a time
    for angle in (0, 10, 0, -10, 0):
        s.value(angle)
        time.sleep(0.6)

for s in servos:
    s.disable()         # go limp
print("done")
