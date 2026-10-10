# Ultrasonic distance test: trigger on GPIO27, echo on GPIO22.
# CHECK THE MODULE VOLTAGE FIRST (see the connections checklist): a 5 V module
# needs a divider on echo before it touches the Pi.
#
#   python3 sensors/ultrasonic_test.py
#
# Prints the median of 5 readings about 4 times a second. Ctrl+C to stop.
import statistics
import time

import gpiod

CHIP = "gpiochip15"
TRIG, ECHO = 27, 22
TIMEOUT_S = 0.03             # ~5 m round trip; longer means no echo
SPEED_CM_S = 34300           # speed of sound at ~20 °C

chip = gpiod.Chip(CHIP)
trig = chip.get_line(TRIG)
trig.request(consumer="us-trig", type=gpiod.LINE_REQ_DIR_OUT)
trig.set_value(0)
echo = chip.get_line(ECHO)
echo.request(consumer="us-echo", type=gpiod.LINE_REQ_DIR_IN)


def measure():
    """One reading in cm, or None if no echo came back."""
    t0 = time.perf_counter()
    while echo.get_value() == 1:              # wait for a leftover echo to end
        if time.perf_counter() - t0 > TIMEOUT_S:
            return None
    trig.set_value(1)
    time.sleep(0.00001)                       # >= 10 us pulse
    trig.set_value(0)
    t0 = time.perf_counter()
    while echo.get_value() == 0:
        if time.perf_counter() - t0 > TIMEOUT_S:
            return None
    start = time.perf_counter()
    while echo.get_value() == 1:
        if time.perf_counter() - start > TIMEOUT_S:
            return None
    return (time.perf_counter() - start) * SPEED_CM_S / 2


print(f"Ultrasonic: trig GPIO{TRIG}, echo GPIO{ECHO}. Ctrl+C to stop.")
try:
    while True:
        vals = []
        for _ in range(5):
            d = measure()
            if d is not None:
                vals.append(d)
            time.sleep(0.04)                  # let echoes die out between pings
        if vals:
            spread = max(vals) - min(vals)
            print(f"{statistics.median(vals):6.1f} cm   (spread {spread:4.1f} cm, {len(vals)}/5 echoes)")
        else:
            print("  no echo (nothing in range, or check wiring / voltage)")
except KeyboardInterrupt:
    print("\nStopped.")
finally:
    trig.set_value(0)
    trig.release()
    echo.release()
    chip.close()
