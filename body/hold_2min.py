import time
from servo import Servo, servo2040
servos = [Servo(servo2040.SERVO_1 + n) for n in range(18)]
try:
    for s in servos:
        s.value(0)
        time.sleep(0.3)
    print("all 18 at neutral, holding 120 s")
    for t in range(120, 0, -15):
        print(t, "s left")
        time.sleep(15)
finally:
    for s in servos:
        s.disable()
    print("done, all limp")
