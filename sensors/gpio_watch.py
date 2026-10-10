# Watch one digital sensor on a Pi GPIO and print each change.
# For the touch module (GPIO17) and the PIR (GPIO4). Both drive the line HIGH when active.
#
#   python3 sensors/gpio_watch.py 17 touch
#   python3 sensors/gpio_watch.py 4 pir
#
# Ctrl+C stops it and prints how many events it saw.
import sys
import time

import gpiod

CHIP = "gpiochip15"          # the Pi 5 header (see docs/system_map.md)
DEBOUNCE_S = 0.02

pin = int(sys.argv[1]) if len(sys.argv) > 1 else 17
name = sys.argv[2] if len(sys.argv) > 2 else f"GPIO{pin}"

chip = gpiod.Chip(CHIP)
line = chip.get_line(pin)
line.request(consumer=f"{name}-watch",
             type=gpiod.LINE_REQ_EV_BOTH_EDGES,
             flags=gpiod.LINE_REQ_FLAG_BIAS_PULL_DOWN)

state = line.get_value()
count = 0
t_on = None
print(f"{name} on GPIO{pin}. Now: {'ON' if state else 'off'}. Ctrl+C to stop.")
if name.lower() == "pir":
    print("PIR: ignore events in the first ~60 s while it warms up.")

try:
    while True:
        if not line.event_wait(1, 0):
            continue
        line.event_read()
        time.sleep(DEBOUNCE_S)
        while line.event_wait(0, 0):          # drop bounce events
            line.event_read()
        new = line.get_value()
        if new == state:
            continue
        state = new
        now = time.monotonic()
        stamp = time.strftime("%H:%M:%S")
        if state:
            count += 1
            t_on = now
            print(f"[{stamp}] {name} ON  #{count}")
        else:
            held = f"{now - t_on:.2f} s" if t_on else "?"
            print(f"[{stamp}] {name} off (lasted {held})")
except KeyboardInterrupt:
    print(f"\nStopped. {count} {name} events.")
finally:
    line.release()
    chip.close()
