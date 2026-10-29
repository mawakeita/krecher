# body/main.py: the Servo 2040's resident program (MicroPython). Body link v0.2.
#
# Streams the six foot sensors and the servo-rail current + voltage to the Pi as JSON lines
# (docs/body_link_protocol.md), and takes pose commands from the Pi without ever blocking,
# so samples keep flowing while the legs move.
#
# Install once (from the Pi, servo venv):
#     mpremote connect /dev/ttyACM0 cp ~/krecher/body/main.py :main.py + reset
# Remove (back to "run one script at a time"):
#     mpremote connect /dev/ttyACM0 rm :main.py + reset
#
# The other body scripts still work with it installed: `mpremote ... run x.py` stops this
# program first (Ctrl+C), and this program makes every servo go limp when it stops.
#
# Safety:
#   * Starts LIMP. Nothing moves until the Pi sends a pose command.
#   * Refuses to pose when the servo rail is below 5.0 V (LiPo unplugged), so servos never
#     wake up all at once when the LiPo goes in later.
#   * If the rail sags below 5.0 V for 0.5 s while posed (brownout / current limit), it goes limp.
#   * Servos switch on one at a time, 0.15 s apart, like stand_up.py.
import sys
import time
import select
import json
from machine import Pin
from pimoroni import Analog, AnalogMux
from servo import Servo, servo2040

FW = "body_link 0.2"

# ---- legs (same as stand_up.py, directions from dir_test.py, Oct 8) ----
FEMUR_DOWN = {"L": -1, "R": 1}
KNEE_OUT = {"L": -1, "R": 1}
LEG_ORDER = ["FL", "ML", "RL", "FR", "MR", "RR"]
LEG_CH = {"FL": ("L", 1), "ML": ("L", 4), "RL": ("L", 7),
          "FR": ("R", 10), "MR": ("R", 13), "RR": ("R", 16)}
POSES = {"crouch": -25, "stand": 10}   # femur angle (pose units), as in stand_up.py
STEP_MS = 80                           # one degree per 80 ms: ~3 s from crouch to stand
ENABLE_GAP_MS = 150                    # servos switch on one at a time
SETTLE_MS = 2000                       # pause in crouch before standing (as stand_up.py)

# ---- sensors ----
FOOT_DOWN_V, FOOT_UP_V = 2.0, 1.0      # switch-era thresholds (hysteresis). Foam feet: retune.
FOOT_STABLE_MS = 20                    # debounce
MIN_RAIL_V = 5.0                       # below this = no LiPo / brownout
BROWNOUT_MS = 500
HIGH_CURRENT_A = 7.0                   # warning only (the buck's CC limit is ~7.9 A)
HIGH_CURRENT_MS = 1000

# ---- hardware ----
mux = AnalogMux(servo2040.ADC_ADDR_0, servo2040.ADC_ADDR_1, servo2040.ADC_ADDR_2,
                muxed_pin=Pin(servo2040.SHARED_ADC))
sense_adc = Analog(servo2040.SHARED_ADC)
cur_adc = Analog(servo2040.SHARED_ADC, servo2040.CURRENT_GAIN,
                 servo2040.SHUNT_RESISTOR, servo2040.CURRENT_OFFSET)
vol_adc = Analog(servo2040.SHARED_ADC, servo2040.VOLTAGE_GAIN)
FOOT_ADDRS = list(range(servo2040.SENSOR_1_ADDR, servo2040.SENSOR_6_ADDR + 1))
for _a in FOOT_ADDRS:
    mux.configure_pull(_a, Pin.PULL_DOWN)

legs = []   # (side, hip, femur, knee)
for _name in LEG_ORDER:
    _side, _ch = LEG_CH[_name]
    legs.append((_side,
                 Servo(servo2040.SERVO_1 + _ch - 1),
                 Servo(servo2040.SERVO_1 + _ch),
                 Servo(servo2040.SERVO_1 + _ch + 1)))


def send(obj):
    sys.stdout.write(json.dumps(obj))
    sys.stdout.write("\n")


# ---- state ----
st = {
    "pose": "limp",      # limp | crouch | stand | moving
    "target": None,      # pose name being moved to
    "theta": None,       # current femur angle in pose units (None = limp)
    "plan": [],          # list of (due_ms, kind, arg)
    "rate_ms": 20,
    "n": 0,
    "a": 0.0,
    "v": 0.0,
    "low_v_since": None,
    "high_a_since": None,
    "high_a_warned": False,
}
foot_v = [0.0] * 6
foot_down = [0] * 6
foot_cand = [0] * 6
foot_cand_since = [0] * 6


def read_feet(now):
    for i in range(6):
        mux.select(FOOT_ADDRS[i])
        v = sense_adc.read_voltage()
        foot_v[i] = v
        if foot_down[i]:
            want = 0 if v < FOOT_UP_V else 1
        else:
            want = 1 if v > FOOT_DOWN_V else 0
        if want == foot_down[i]:
            foot_cand[i] = want
            continue
        if foot_cand[i] != want:
            foot_cand[i] = want
            foot_cand_since[i] = now
        elif time.ticks_diff(now, foot_cand_since[i]) >= FOOT_STABLE_MS:
            foot_down[i] = want
            send({"k": "f", "t": now, "leg": LEG_ORDER[i], "down": want, "fv": round(v, 2)})


def read_rail():
    mux.select(servo2040.VOLTAGE_SENSE_ADDR)
    st["v"] = vol_adc.read_voltage()
    mux.select(servo2040.CURRENT_SENSE_ADDR)
    st["a"] = cur_adc.read_current()


def all_limp():
    for _, hip, fem, knee in legs:
        hip.disable()
        fem.disable()
        knee.disable()
    st["pose"] = "limp"
    st["target"] = None
    st["theta"] = None
    st["plan"] = []


def apply_theta(theta):
    for side, hip, fem, knee in legs:
        fem.value(FEMUR_DOWN[side] * theta)
        knee.value(KNEE_OUT[side] * theta)
    st["theta"] = theta


def enable_one(i):
    # i = 0..17: leg i // 3, joint i % 3 (hip, femur, knee), into the crouch pose
    side, hip, fem, knee = legs[i // 3]
    j = i % 3
    c = POSES["crouch"]
    if j == 0:
        hip.value(0)
    elif j == 1:
        fem.value(FEMUR_DOWN[side] * c)
    else:
        knee.value(KNEE_OUT[side] * c)


def plan_pose(name, now):
    """Build a non-blocking plan to reach a named pose. Returns an error string or None."""
    if st["v"] < MIN_RAIL_V:
        return "no_servo_power"
    if name == st["pose"]:
        return None
    plan = []
    due = now
    theta = st["theta"]
    if theta is None:                      # from limp: switch on one servo at a time into crouch
        for i in range(18):
            plan.append((due, "enable", i))
            due = time.ticks_add(due, ENABLE_GAP_MS)
        theta = POSES["crouch"]
        plan.append((due, "theta_set", theta))
        if name != "crouch":
            due = time.ticks_add(due, SETTLE_MS)
    goal = POSES[name]
    step = 1 if goal > theta else -1
    for t in range(theta, goal, step):
        due = time.ticks_add(due, STEP_MS)
        plan.append((due, "theta", t + step))
    plan.append((due, "done", name))
    st["plan"] = plan
    st["target"] = name
    st["pose"] = "moving"
    return None


def run_plan(now):
    plan = st["plan"]
    while plan and time.ticks_diff(now, plan[0][0]) >= 0:
        _, kind, arg = plan.pop(0)
        if kind == "enable":
            enable_one(arg)
        elif kind == "theta_set":
            st["theta"] = arg
        elif kind == "theta":
            apply_theta(arg)
        elif kind == "done":
            st["pose"] = arg
            st["target"] = None
            send({"k": "pose_done", "t": now, "name": arg})


def check_power(now):
    # brownout while posed -> limp
    if st["pose"] != "limp" and st["v"] < MIN_RAIL_V:
        if st["low_v_since"] is None:
            st["low_v_since"] = now
        elif time.ticks_diff(now, st["low_v_since"]) >= BROWNOUT_MS:
            all_limp()
            send({"k": "w", "t": now, "msg": "undervolt", "v": round(st["v"], 2), "action": "limp"})
            st["low_v_since"] = None
    else:
        st["low_v_since"] = None
    # sustained high current -> warning (once per episode)
    if st["a"] > HIGH_CURRENT_A:
        if st["high_a_since"] is None:
            st["high_a_since"] = now
        elif not st["high_a_warned"] and time.ticks_diff(now, st["high_a_since"]) >= HIGH_CURRENT_MS:
            send({"k": "w", "t": now, "msg": "overcurrent", "a": round(st["a"], 2)})
            st["high_a_warned"] = True
    else:
        st["high_a_since"] = None
        st["high_a_warned"] = False


def handle(line, now):
    try:
        cmd = json.loads(line)
        k = cmd["k"]
    except Exception:
        send({"k": "ack", "t": now, "ok": 0, "msg": "bad_json"})
        return
    if k == "ping":
        send({"k": "pong", "t": now, "id": cmd.get("id", 0)})
    elif k == "hi":
        send({"k": "hello", "fw": FW, "feet": ",".join(LEG_ORDER), "pose": st["pose"]})
    elif k == "limp":
        all_limp()
        send({"k": "ack", "t": now, "cmd": "limp", "ok": 1})
    elif k == "rate":
        hz = max(10, min(100, int(cmd.get("hz", 50))))
        st["rate_ms"] = 1000 // hz
        send({"k": "ack", "t": now, "cmd": "rate", "ok": 1, "hz": hz})
    elif k == "pose":
        name = cmd.get("name", "")
        if name == "limp":
            all_limp()
            send({"k": "ack", "t": now, "cmd": "pose", "name": name, "ok": 1})
        elif name not in POSES:
            send({"k": "ack", "t": now, "cmd": "pose", "name": name, "ok": 0, "msg": "unknown_pose"})
        else:
            err = plan_pose(name, now)
            if err:
                send({"k": "ack", "t": now, "cmd": "pose", "name": name, "ok": 0, "msg": err,
                      "v": round(st["v"], 2)})
            else:
                send({"k": "ack", "t": now, "cmd": "pose", "name": name, "ok": 1})
                if st["pose"] == name:
                    send({"k": "pose_done", "t": now, "name": name})
    else:
        send({"k": "ack", "t": now, "ok": 0, "msg": "unknown_cmd"})


poller = select.poll()
poller.register(sys.stdin, select.POLLIN)
inbuf = []


def read_commands(now):
    while poller.poll(0):
        ch = sys.stdin.read(1)
        if not ch:
            break
        if ch == "\n" or ch == "\r":
            if inbuf:
                handle("".join(inbuf), now)
                del inbuf[:]
        elif len(inbuf) < 200:
            inbuf.append(ch)


def sample(now):
    st["n"] += 1
    th = st["theta"]
    sys.stdout.write('{"k":"s","t":%d,"n":%d,"feet":[%d,%d,%d,%d,%d,%d],'
                     '"fv":[%.2f,%.2f,%.2f,%.2f,%.2f,%.2f],"a":%.2f,"v":%.2f,"p":"%s","th":%s}\n' % (
                         now, st["n"], foot_down[0], foot_down[1], foot_down[2], foot_down[3],
                         foot_down[4], foot_down[5], foot_v[0], foot_v[1], foot_v[2], foot_v[3],
                         foot_v[4], foot_v[5], st["a"], st["v"], st["pose"],
                         "null" if th is None else str(th)))


def main():
    all_limp()
    send({"k": "hello", "fw": FW, "feet": ",".join(LEG_ORDER), "pose": "limp"})
    next_s = time.ticks_ms()
    while True:
        now = time.ticks_ms()
        read_commands(now)
        read_feet(now)
        run_plan(now)
        if time.ticks_diff(now, next_s) >= 0:
            read_rail()
            check_power(now)
            sample(now)
            next_s = time.ticks_add(next_s, st["rate_ms"])
            if time.ticks_diff(now, next_s) > 0:     # fell behind: don't burst to catch up
                next_s = time.ticks_add(now, st["rate_ms"])
        time.sleep_ms(2)


try:
    main()
finally:
    all_limp()
