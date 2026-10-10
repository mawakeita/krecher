# Foot-switch test on the Servo 2040's six sensor headers (MicroPython, runs ON the Servo 2040).
# From the Pi:  mpremote connect /dev/ttyACM0 run ~/krecher/body/feet_test.py
#
# Wiring per foot: switch COM -> header signal pin, switch NO -> header 3V3 pin.
# Foot down = switch closed = ~3.3 V. The pull-down set below holds an open switch at 0 V.
import time
from machine import Pin
from pimoroni import Analog, AnalogMux
from servo import servo2040

NAMES = ["FL", "ML", "RL", "FR", "MR", "RR"]   # sensor headers 1-6
DOWN_V, UP_V = 2.0, 1.0                        # hysteresis: above 2.0 V = down, below 1.0 V = up
SECONDS = 120                                  # stops by itself after 2 minutes

adc = Analog(servo2040.SHARED_ADC)
mux = AnalogMux(servo2040.ADC_ADDR_0, servo2040.ADC_ADDR_1, servo2040.ADC_ADDR_2,
                muxed_pin=Pin(servo2040.SHARED_ADC))
addrs = list(range(servo2040.SENSOR_1_ADDR, servo2040.SENSOR_6_ADDR + 1))
for a in addrs:
    mux.configure_pull(a, Pin.PULL_DOWN)


def volts(i):
    mux.select(addrs[i])
    return adc.read_voltage()


start_v = [volts(i) for i in range(6)]
down = [v > DOWN_V for v in start_v]
print("start:", "  ".join("%s %.2fV %s" % (NAMES[i], start_v[i], "DOWN" if down[i] else "up")
                          for i in range(6)))
print("Press each foot switch in turn. Stops after %d s." % SECONDS)

t_end = time.ticks_add(time.ticks_ms(), SECONDS * 1000)
changes = 0
while time.ticks_diff(t_end, time.ticks_ms()) > 0:
    for i in range(6):
        v = volts(i)
        if not down[i] and v > DOWN_V:
            down[i] = True
        elif down[i] and v < UP_V:
            down[i] = False
        else:
            continue
        changes += 1
        print("%8d ms  %s %s  (%.2f V)" % (time.ticks_ms(), NAMES[i], "DOWN" if down[i] else "up", v))
    time.sleep_ms(10)
print("done, %d changes" % changes)
