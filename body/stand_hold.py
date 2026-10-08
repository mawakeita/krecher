import time
from servo import Servo, servo2040

# Stand test: all 18 to the middle (standing pose), hold 20 s, then limp.
# Keep a box under the body: it lands there when the servos go limp.
servos = [Servo(servo2040.SERVO_1 + n - 1) for n in range(1, 19)]
try:
    for n, s in enumerate(servos, start=1):
        s.value(0)
        time.sleep(0.3)
    print("all 18 holding - let go of the body slowly")
    for t in range(20, 0, -5):
        print(t, "s left")
        time.sleep(5)
finally:
    for s in servos:
        s.disable()
    print("done, all limp")
