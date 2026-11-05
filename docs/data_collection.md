# Data collection: teaching krēCHer what's happening to it

**Status: written Oct 28, 2026, tested end to end with simulated sensors only.** First real run still to do.

krēCHer goes through a fixed set of tests (standing, being touched, approached, picked up, carried, shaken…). Every sensor is logged on the Pi's clock while each test is labelled, so the logs become a dataset a model can learn from. This is the Independent Study pipeline: **event set → data collection protocol → labelled dataset → model → on-device vs server comparison.**

| File | Runs on | What it does |
| --- | --- | --- |
| `body/main.py` | Servo 2040 | Body link 0.2: streams feet, rail current + voltage, pose at 50 Hz; takes `stand` / `crouch` / `limp` from the Pi ([protocol](body_link_protocol.md)) |
| `sensors/logger.py` | Pi | Logs IMU, touch, PIR, ultrasonic, body link and a camera still every 10 s into one file; runs the tests and labels them |
| `sensors/protocols.py` | (edited by you) | The tests: labels, times, spoken instructions |
| `learn/make_dataset.py` | Pi or Mac | Cuts the logs into 1 s windows → `learn/dataset.csv` |
| `learn/train.py` | Mac (or Pi) | Trains a random forest, tests it on sessions it hasn't seen, reports accuracy and prediction time |

## What gets logged

| Source | Rate | Fields | Feeds |
| --- | --- | --- | --- |
| BNO085 | 50 Hz | quaternion, roll/pitch/yaw (°), accel (m/s²), gyro (rad/s) | picked up, carried, shaken, rotated, bumped |
| Touch (GPIO17) | on change | 0/1 | touched |
| PIR (GPIO4) | on change | 0/1 | someone near |
| Ultrasonic (GPIO27/22) | 10 Hz | distance in cm, `null` = no echo | approached vs passing by |
| Body link | 50 Hz | 6 foot voltages, rail current + voltage, pose, femur angle | standing / moving itself, bumped, (later) lifted |
| Camera | every 10 s | 1280 × 720 JPEG, named by the log clock | checking labels by eye (~50 MB/hr) |

Not logged yet: the mic, the head battery level.

## The tests (`--protocol full`, ~15 min for 3 reps)

**Block A, floor (LiPo in, legs powered):** rest limp → stand up → stand still → touch tap → touch hold → approach → pass by → pet → bump → sit down → crouch still.

**Block B, handling (LiPo out, legs limp, head on its own battery):** rest on floor → pick up → hold still → carry → rotate → shake → put down → rest on floor.

Why the LiPo comes out for Block B: it's still tethered on the bench (Oct 27 decision), so lifting krēCHer with it plugged in would tug the leads. The head runs on its own 2S battery and the Servo 2040 stays alive on USB, so every sensor keeps logging. Once the LiPo is strapped under the plate, add a "picked up while standing" test: the leg current dropping as the feet leave the floor is a strong signal.

Labels are **states** (resting, held, carried). The study's **events** are the changes between them (picked up = resting → held). `learn/train.py --grouped` merges the labels into the study's event names.

## How to run it

**0 · Get the code onto the Pi.** Copy the files into `~/krecher` on the Mac, push, then on the Pi `cd ~/krecher && git pull`.

**1 · Install the body link (once).** Body on the box, LiPo **out**:

```
source ~/venvs/servo/bin/activate
mpremote connect /dev/ttyACM0 cp ~/krecher/body/main.py :main.py + reset
```

From now on the Servo 2040 runs it at every power-up, **starting limp**. `stand_up.py`, `hold_2min.py` etc. still work as before (`mpremote … run` stops it first, and it goes limp when stopped). To remove it: `mpremote connect /dev/ttyACM0 rm :main.py + reset`.

**2 · Check every sensor (5 s, nothing saved).**

```
source ~/venvs/imu/bin/activate
pip install pyserial            # only if the check says "No module named 'serial'"
python3 sensors/logger.py --check
```

Expect: imu ~50/s, body ~50/s, us ~10/s, touch and pir one line each (more if you touch / move), cam one still. If the IMU logs errors at 50 Hz, use `--imu-hz 20` (Exp 02's rate). The logger owns `/dev/ttyACM0` while it runs, so close any `mpremote` first.

**3 · Rehearse once** (short, to learn the rhythm): `python3 sensors/logger.py --protocol floor --reps 1`

**4 · A full session:** `python3 sensors/logger.py`

- Each test: instruction printed and spoken, 3-2-1, then it records. Block changes wait for Enter.
- Something went wrong in a test (tripped, wrong move, someone walked in)? Type **x** + Enter during it: that test is dropped later. Any other text + Enter is saved as a note.
- Ctrl+C at any time: legs go limp, the log and summary are saved.
- Read the summary at the end: rates near 50/s, `lost 0`, few errors.

**5 · Free play** (real-life data, unscripted): `python3 sensors/logger.py --free`. Type a label + Enter to start it (`picked_up`), empty Enter to stop. `!stand`, `!crouch`, `!limp` move the body.

**6 · Bring the data to the Mac.** `data/` is not committed (too big for git):

```
rsync -av krecher:~/krecher/data/ ~/krecher/data/
```

**7 · Learn.** On the Mac (`pip install scikit-learn joblib` once):

```
python3 learn/make_dataset.py
python3 learn/train.py
python3 learn/train.py --grouped
```

## How much data

- **At least 3 sessions, on different days** (ideally a different room, and another person doing some tests). The trainer only ever tests on a session it didn't train on, so its score says how krēCHer will do on a new day, not how well it memorised today.
- One full session (3 reps) ≈ 1,200 labelled windows.
- Pay attention to the "mistaken for" column: pairs like pick_up / put_down or touch_hold / pet tell you which tests need more reps or a sensor that can tell them apart.

## Rehearse without the robot

Simulated sensors, no hardware, any machine:

```
python3 sensors/logger.py --dry-run --yes --time-scale 0.2 --reps 1
python3 learn/make_dataset.py --include-dry && python3 learn/train.py
```

The simulated signals are made up, so their high scores mean only that the pipeline works, not that krēCHer will learn this well.

## Log format

One JSON object per line in `data/<date>/<time>_<protocol>.jsonl`. Every line has `t` (Pi `time.monotonic()`, seconds) and `src`:

```
{"t":512.031,"src":"meta","session":"193012_full","protocol":"full","git":"1cf3701","sources":{...}}
{"t":530.120,"src":"label","label":"pick_up","edge":"start","block":"handling","rep":1,"trial":2}
{"t":530.141,"src":"imu","q":[...],"rpy":[1.2,-0.4,88.0],"acc":[0.1,0.2,9.8],"gyr":[0.0,0.01,0.0]}
{"t":530.150,"src":"body","k":"s","bt":81234,"n":4012,"feet":[0,0,0,0,0,0],"fv":[...],"a":0.15,"v":0.0,"p":"limp","th":null}
{"t":530.180,"src":"us","cm":87.5}
{"t":531.004,"src":"touch","v":1}
{"t":538.120,"src":"label","label":"pick_up","edge":"end","bad":0}
{"t":540.000,"src":"cam","file":"193012_full_cam/cam_0000540.00.jpg"}
```

Other `src` values: `pir`, `mark` (an x), `note`, `err`, `body_raw` (non-JSON from the Servo 2040), `meta_end`.

## Known limits

- **Feet are off** (redesign with ESD foam). Their voltages log as ~0 for now; once foam feet are in, the same `fv` field carries how hard each foot presses, with no code change. The `feet` 0/1 thresholds in `body/main.py` (2.0 / 1.0 V) will need retuning for foam.
- `body/main.py` has only run in a simulator here. First real run: body on the box, LiPo out, `--check`, then `--protocol floor --reps 1`.
- The IMU's yaw uses the magnetometer, which the servos and buck may disturb. Turning features use the gyro, which isn't affected.
- Next step after training: a `learn/live.py` that runs the saved model on the Pi every 0.5 s (on-device inference), and the same model on the Oracle node for the comparison.
