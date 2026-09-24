import gpiod
import time
from datetime import timedelta

chip = gpiod.Chip("gpiochip15")
line = chip.get_line(17)
line.request(
    consumer="touch-test",
    type=gpiod.LINE_REQ_EV_BOTH_EDGES,
    flags=gpiod.LINE_REQ_FLAG_BIAS_PULL_UP,
)

last_state = line.get_value()  # 1 = released, 0 = pressed

print("--------------------------------------------------")
print("KreCHer Experiment 01: Active and Listening")
print("Press the micro-switch lever. Ctrl+C to quit.")
print("--------------------------------------------------")

try:
    while True:
        if line.event_wait(1, 0):
            line.event_read()
            time.sleep(0.05)  # let switch bounce settle (50 ms debounce)
            while line.event_wait(0, 0):
                line.event_read()  # discard bounce events
            state = line.get_value()
            if state != last_state:
                stamp = time.strftime("%H:%M:%S")
                if state == 0:
                    print(f"[{stamp}] KreCHer: PHYSICAL TOUCH REGISTERED")
                else:
                    print(f"[{stamp}] KreCHer: TOUCH RELEASED")
                last_state = state
except KeyboardInterrupt:
    print("Stopped.")
finally:
    line.release()
    chip.close()
