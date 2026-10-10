# Servo-rail current and voltage test (MicroPython, runs ON the Servo 2040).
# From the Pi:  mpremote connect /dev/ttyACM0 run ~/krecher/body/rail_test.py
#
# Body on the boxes, servo power on (6.0 V, CC 3 A). It reads for 5 s with the legs limp,
# moves all 18 servos to middle one at a time, holds 15 s, then goes limp and reads 5 s more.
import time
from machine import Pin
from pimoroni import Analog, AnalogMux
from servo import Servo, servo2040

mux = AnalogMux(servo2040.ADC_ADDR_0, servo2040.ADC_ADDR_1, servo2040.ADC_ADDR_2,
                muxed_pin=Pin(servo2040.SHARED_ADC))
cur_adc = Analog(servo2040.SHARED_ADC, servo2040.CURRENT_GAIN,
                 servo2040.SHUNT_RESISTOR, servo2040.CURRENT_OFFSET)
vol_adc = Analog(servo2040.SHARED_ADC, servo2040.VOLTAGE_GAIN)

peak = 0.0


def report(label, seconds):
    global peak
    t_end = time.ticks_add(time.ticks_ms(), int(seconds * 1000))
    while time.ticks_diff(t_end, time.ticks_ms()) > 0:
        mux.select(servo2040.VOLTAGE_SENSE_ADDR)
        v = vol_adc.read_voltage()
        mux.select(servo2040.CURRENT_SENSE_ADDR)
        a = cur_adc.read_current()
        peak = max(peak, a)
        print("%-6s %5.2f V  %5.2f A" % (label, v, a))
        time.sleep_ms(500)


servos = [Servo(servo2040.SERVO_1 + n) for n in range(18)]
try:
    print("limp, 5 s")
    report("limp", 5)
    print("all 18 to middle, one at a time")
    for s in servos:
        s.value(0)
        time.sleep_ms(150)
    report("hold", 15)
finally:
    for s in servos:
        s.disable()
    print("all limp")
report("limp", 5)
print("peak current %.2f A" % peak)
