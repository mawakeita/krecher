# channel_check.py: move ONE channel at a time and watch which joint answers.
# For each channel 1..18: middle -> +15 deg (2 s) -> middle, then limp before the next.
# Watch two things each time: is it the joint the label says, and does ANY other joint move too?
#
# Body on the box (legs hanging free). USB + Pi first, LiPo last.
#   source ~/venvs/servo/bin/activate
#   mpremote connect /dev/ttyACM0 run ~/krecher/body/channel_check.py
#
# Only want a few channels? Edit ONLY below, e.g. ONLY = [1, 2, 3, 16, 17, 18]
import time
from servo import Servo, servo2040

ONLY = None

NAMES = {}
for leg, first in (("FL", 1), ("ML", 4), ("RL", 7), ("FR", 10), ("MR", 13), ("RR", 16)):
    for i, joint in enumerate(("hip", "femur", "knee")):
        NAMES[first + i] = leg + " " + joint

channels = ONLY or list(range(1, 19))
s = None
try:
    print("Channel check. Each channel moves +15 deg for 2 s, then goes limp.")
    time.sleep(3)
    for ch in channels:
        s = Servo(servo2040.SERVO_1 + ch - 1)
        print("ch", ch, "=", NAMES[ch], "... moving now")
        s.value(0);  time.sleep(0.8)
        s.value(15); time.sleep(2)
        s.value(0);  time.sleep(0.8)
        s.disable(); s = None
        time.sleep(1.5)
finally:
    if s is not None:
        s.disable()
    print("done, all limp")
