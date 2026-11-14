# Foam test: live voltage of the six foot wires on the Servo 2040 (MicroPython, runs ON the Servo 2040).
# From the Pi (LiPo not needed):
#     mpremote connect /dev/ttyACM0 run ~/krecher/body/foam_test.py
# Afterwards, unplug and replug the Servo 2040's USB so main.py runs again.
#
# Wiring as the switches were: one wire on the header's signal pin, one on its 3V3 pin.
# Put a piece of foam between the two wire ends: squeezing it should make the voltage go UP.
# The board's own pull-down acts as the resistor to GND, so no resistor is needed for this test.
import time
from machine import Pin
from pimoroni import Analog, AnalogMux
from servo import servo2040

NAMES = ["FL", "ML", "RL", "FR", "MR", "RR"]   # sensor headers 1-6
SECONDS = 90

adc = Analog(servo2040.SHARED_ADC)
mux = AnalogMux(servo2040.ADC_ADDR_0, servo2040.ADC_ADDR_1, servo2040.ADC_ADDR_2,
                muxed_pin=Pin(servo2040.SHARED_ADC))
addrs = list(range(servo2040.SENSOR_1_ADDR, servo2040.SENSOR_6_ADDR + 1))
for a in addrs:
    mux.configure_pull(a, Pin.PULL_DOWN)


def volts(i):
    mux.select(addrs[i])
    time.sleep_ms(2)
    return adc.read_voltage()


print("Squeeze the foam and watch its number. Stops after %d s." % SECONDS)
t_end = time.ticks_add(time.ticks_ms(), SECONDS * 1000)
while time.ticks_diff(t_end, time.ticks_ms()) > 0:
    print("   ".join("%s %.2f V" % (NAMES[i], volts(i)) for i in range(6)))
    time.sleep_ms(300)
print("done")
