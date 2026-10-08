import time
from servo import Servo, servo2040

# Direction test: +20 deg on one femur and one knee per side, one at a time.
def nudge(ch, name):
    s = Servo(servo2040.SERVO_1 + ch - 1)
    s.value(0); time.sleep(1)
    print(name, "-> +20 now")
    s.value(20); time.sleep(2.5)
    s.value(0); time.sleep(1)
    s.disable()

try:
    nudge(2,  "1) FL femur (ch 2):  did the KNEE END go UP or DOWN?")
    nudge(3,  "2) FL knee  (ch 3):  did the FOOT swing OUT (away from body) or IN?")
    nudge(11, "3) FR femur (ch 11): did the KNEE END go UP or DOWN?")
    nudge(12, "4) FR knee  (ch 12): did the FOOT swing OUT or IN?")
finally:
    print("done")
