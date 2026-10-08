import time
from servo import Servo, servo2040

# All 18 leg servos to the middle, one at a time, each with a small nod so you can see it react.
servos = [Servo(servo2040.SERVO_1 + n - 1) for n in range(1, 19)]
try:
    for n, s in enumerate(servos, start=1):
        s.value(0)
        time.sleep(0.2)
        s.value(10)
        time.sleep(0.3)
        s.value(0)
        print("servo", n, "middle")
        time.sleep(0.3)
    print("holding 30 s - press a leg gently: it should resist")
    time.sleep(30)
finally:
    for s in servos:
        s.disable()
    print("done, all limp")
