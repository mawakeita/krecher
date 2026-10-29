"""Test protocols for sensors/logger.py: what krēCHer goes through, in order.

Each trial is one labelled stretch of the log. The label names the STATE krēCHer is in
(resting, held, carried, being touched...). The events the independent study wants
(picked up, put down, touched, approached...) are the changes between those states,
so the model learns the states and the events fall out of the transitions.

Trial fields:
    label   name written into the log (and later the dataset)
    secs    how long to record. None = "until the body says the pose is reached"
    say     the instruction, printed and spoken
    body    pose command sent to the Servo 2040 at the start: "stand", "crouch", "limp" or None

Edit freely: add trials, change times. Keep labels lowercase_with_underscores, and keep a
label's meaning the same across sessions, or the sessions can't be learned together.
"""

# Block A: LiPo PLUGGED IN, krēCHer on the floor (or the box). Legs powered.
FLOOR = {
    "name": "floor",
    "power": True,
    "setup": [
        "Body on the floor if it already stands safely there, otherwise on the box.",
        "Power order: Pi + USB first, LiPo last. Clear about 6 ft in front of krēCHer.",
        "Stand to the side, out of the ultrasonic's view, between trials.",
    ],
    "trials": [
        {"label": "rest_limp", "secs": 15, "body": "limp",
         "say": "Legs limp, resting. Don't touch it, stay back."},
        {"label": "stand_up", "secs": None, "body": "stand",
         "say": "Standing up. Hands off."},
        {"label": "stand_still", "secs": 20,
         "say": "Standing still. Stay six feet away, don't touch."},
        {"label": "touch_tap", "secs": 12,
         "say": "Tap the touch spot, about once a second."},
        {"label": "touch_hold", "secs": 12,
         "say": "Rest your hand on the touch spot and keep it there."},
        {"label": "approach", "secs": 15,
         "say": "Start six feet in front. Walk slowly up to about a foot away, pause, then back away."},
        {"label": "pass_by", "secs": 12,
         "say": "Walk past its front, about three feet away, without stopping."},
        {"label": "pet", "secs": 12,
         "say": "Stroke its back and head gently, avoiding the touch spot."},
        {"label": "bump", "secs": 10,
         "say": "Give the body two or three gentle pushes from the side. Not the legs."},
        {"label": "sit_down", "secs": None, "body": "crouch",
         "say": "Sitting down. Hands off."},
        {"label": "crouch_still", "secs": 15,
         "say": "Crouched and still. Stay back."},
    ],
}

# Block B: LiPo UNPLUGGED, legs limp, head on its own battery. Safe to pick up.
HANDLING = {
    "name": "handling",
    "power": False,
    "setup": [
        "Unplug the LiPo now (legs go limp; the head keeps running on its own battery).",
        "Move the LiPo away so nothing tugs on the leads.",
        "krēCHer on the floor. Hold it by the body plates, never by the legs or head.",
    ],
    "trials": [
        {"label": "rest_floor", "secs": 15, "body": "limp",
         "say": "On the floor, resting. Hands off."},
        {"label": "pick_up", "secs": 8,
         "say": "Lift it off the floor with both hands, up to chest height, and hold it."},
        {"label": "held_still", "secs": 10,
         "say": "Keep holding it as still as you can."},
        {"label": "carry", "secs": 20,
         "say": "Walk around the room carrying it level."},
        {"label": "rotate", "secs": 15,
         "say": "Slowly turn and tilt it in your hands, in different directions."},
        {"label": "shake", "secs": 6,
         "say": "Shake it gently. Small, quick movements."},
        {"label": "put_down", "secs": 8,
         "say": "Put it down on the floor, let go and step back."},
        {"label": "rest_floor", "secs": 10,
         "say": "Resting on the floor. Hands off."},
    ],
}

PROTOCOLS = {
    "full": [FLOOR, HANDLING],     # ~5 min per rep, plus setup pauses
    "floor": [FLOOR],
    "handling": [HANDLING],
}
