from fusion_hat.servo import Servo
from time import sleep

PAN, TILT = 2, 3  # PWM channels, same as SunFounder's pan-tilt example
pan, tilt = Servo(PAN), Servo(TILT)

pan.angle(0); tilt.angle(0)
print("Centered: pan 0, tilt 0. Check the camera looks straight ahead.")
input("Press Enter for a gentle movement test (Ctrl+C to skip)... ")

for a in (-30, 30, 0):
    pan.angle(a); print("pan", a); sleep(1)
for a in (-20, 20, 0):
    tilt.angle(a); print("tilt", a); sleep(1)
print("Done, back at center.")
