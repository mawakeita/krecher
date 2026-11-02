# walk_tripod.py: tripod gait for krēCHer (open loop, timed, like RHex).
# Tripod A = FL, MR, RL; tripod B = FR, ML, RR. While one tripod lifts and swings
# forward, the other stays down and pushes back; then they swap.
#
# Run (body on the box for every first try of a mode):
#   source ~/venvs/servo/bin/activate
#   mpremote connect /dev/ttyACM0 run ~/krecher/body/walk_tripod.py
# Change MODE (and the numbers below it) in this file between runs.
# Ctrl+C at any time: all 18 servos go limp.
import time
from servo import Servo, servo2040

# ---------------- settings ----------------
MODE     = "march"   # "hip_check" -> "march" -> "walk" -> "turn"
CYCLES   = 5             # full cycles (A step + B step)
HIP_STEP = 10            # degrees each hip swings from centre (start 10, max ~15)
LIFT     = 20            # pose units the femur rises when a leg lifts (more = higher step)
CYCLE_S  = 1.6           # seconds per full cycle (bigger = slower, steadier)
TURN_DIR = "left"        # for MODE = "turn"

# Which hip sign moves each foot FORWARD. From hip_check on the box, Nov 1:
# left legs swing forward on +, right legs swing backward on + (mirrored).
HIP_FWD = {"FL": 1, "ML": 1, "RL": 1, "FR": -1, "MR": -1, "RR": -1}
# ------------------------------------------

FEMUR_DOWN = {"L": -1, "R": 1}   # from dir_test.py, Oct 8
KNEE_OUT   = {"L": -1, "R": 1}
LEGS = {"FL": ("L", 1), "ML": ("L", 4), "RL": ("L", 7),
        "FR": ("R", 10), "MR": ("R", 13), "RR": ("R", 16)}
TRIPOD_A = ("FL", "MR", "RL")
TRIPOD_B = ("FR", "ML", "RR")

CROUCH = -25
STAND  = 10
STEP_S = 0.08
DT     = 0.02

legs = {}
for name, (side, ch) in LEGS.items():
    legs[name] = (side,
                  Servo(servo2040.SERVO_1 + ch - 1),   # hip
                  Servo(servo2040.SERVO_1 + ch),       # femur
                  Servo(servo2040.SERVO_1 + ch + 1))   # knee

hip_pos = {n: 0.0 for n in LEGS}     # where each hip is now (degrees)

def fem_stand(n): return FEMUR_DOWN[legs[n][0]] * STAND
def fem_up(n):    return FEMUR_DOWN[legs[n][0]] * (STAND - LIFT)

def pose(theta):
    for side, hip, fem, knee in legs.values():
        fem.value(FEMUR_DOWN[side] * theta)
        knee.value(KNEE_OUT[side] * theta)

def ramp(a, b):
    step = 1 if b > a else -1
    for t in range(a, b + step, step):
        pose(t)
        time.sleep(STEP_S)

def glide(moves, secs):
    """moves: list of (servo, start, end); move together, eased, over secs."""
    n = max(1, int(secs / DT))
    for i in range(1, n + 1):
        f = i / n
        f = f * f * (3 - 2 * f)
        for s, a, b in moves:
            s.value(a + (b - a) * f)
        time.sleep(DT)

def hip_target(n, forward):
    """Hip angle that puts leg n's foot forward (forward=True) or back."""
    if MODE == "turn":
        # turning left: left feet push back, right feet push forward (and vice versa)
        spin = {"L": -1, "R": 1}[legs[n][0]]
        if TURN_DIR == "right":
            spin = -spin
        d = HIP_FWD[n] * spin
    else:
        d = HIP_FWD[n]
    return d * HIP_STEP * (1 if forward else -1)

def half_step(swing, stance, swing_hips=True):
    """Lift the swing tripod, swing it forward while the stance tripod pushes back, put it down."""
    t = CYCLE_S / 2
    glide([(legs[n][2], fem_stand(n), fem_up(n)) for n in swing], t * 0.25)       # lift
    if swing_hips:
        moves = []
        for n in swing:
            end = hip_target(n, True);  moves.append((legs[n][1], hip_pos[n], end)); hip_pos[n] = end
        for n in stance:
            end = hip_target(n, False); moves.append((legs[n][1], hip_pos[n], end)); hip_pos[n] = end
        glide(moves, t * 0.5)                                                       # swing + push
    else:
        time.sleep(t * 0.5)
    glide([(legs[n][2], fem_up(n), fem_stand(n)) for n in swing], t * 0.25)       # down

def recentre():
    """Bring every hip back to 0, one tripod at a time, feet lifted while moving."""
    for tri in (TRIPOD_A, TRIPOD_B):
        glide([(legs[n][2], fem_stand(n), fem_up(n)) for n in tri], 0.3)
        glide([(legs[n][1], hip_pos[n], 0) for n in tri], 0.4)
        for n in tri:
            hip_pos[n] = 0
        glide([(legs[n][2], fem_up(n), fem_stand(n)) for n in tri], 0.3)

if MODE not in ("hip_check", "march", "walk", "turn"):
    raise ValueError("MODE must be hip_check, march, walk or turn")

try:
    print("crouch: lifting the feet, one servo at a time")
    for s, h, f, k in legs.values():
        h.value(0);                        time.sleep(0.15)
        f.value(FEMUR_DOWN[s] * CROUCH);   time.sleep(0.15)
        k.value(KNEE_OUT[s] * CROUCH);     time.sleep(0.15)
    time.sleep(2)
    print("standing up...")
    ramp(CROUCH, STAND)
    time.sleep(1.5)

    if MODE == "hip_check":
        print("hip check: each leg swings its hip +10 deg, holds 2 s, returns.")
        print("For each leg, note: did the foot move toward the FRONT or the BACK?")
        for n in ("FL", "ML", "RL", "FR", "MR", "RR"):
            hip = legs[n][1]
            print("  ", n, "...")
            glide([(hip, 0, 10)], 0.6)
            time.sleep(2)
            glide([(hip, 10, 0)], 0.6)
            time.sleep(1)
    else:
        print(MODE, CYCLES, "cycles, hip step", HIP_STEP, "lift", LIFT, "cycle", CYCLE_S, "s")
        for c in range(CYCLES):
            print("  cycle", c + 1)
            half_step(TRIPOD_A, TRIPOD_B, swing_hips=(MODE != "march"))
            half_step(TRIPOD_B, TRIPOD_A, swing_hips=(MODE != "march"))
        if MODE != "march":
            recentre()
        print("done walking - holding 2 s")
        time.sleep(2)

    print("sitting down...")
    ramp(STAND, CROUCH)
    time.sleep(2)
finally:
    for _, h_, f_, k_ in legs.values():
        h_.disable(); f_.disable(); k_.disable()
    print("done, all limp")
