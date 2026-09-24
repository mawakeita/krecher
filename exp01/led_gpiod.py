import gpiod
import time

chip = gpiod.Chip("gpiochip15")
line = chip.get_line(21)
line.request(consumer="led-test", type=gpiod.LINE_REQ_DIR_OUT, default_val=0)

line.set_value(1)
print("LED on")
time.sleep(3)
line.set_value(0)
print("LED off")

line.release()
chip.close()
