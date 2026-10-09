# Body link: Servo 2040 ↔ Pi message format

**Status: draft (Oct 9).** Nothing implemented yet. This is the contract for the code on both sides.

The Servo 2040 reads the six foot switches and its own servo-rail current and voltage, and streams them to the Pi over the USB serial port it already uses. The Pi logs everything next to the IMU, touch, ultrasonic and PIR data, so the independent study's dataset has one clock (see [`system_map.md`](system_map.md), section 5).

## Transport

- USB serial (the Servo 2040 appears on the Pi as `/dev/ttyACM0`). No extra wires.
- One JSON object per line, ending in `\n`. Easy to read by eye, easy to parse in Python on both sides (`json` on the Pi, `json` in MicroPython).
- Anything that isn't valid JSON (a MicroPython traceback, a `print` while debugging) is logged by the Pi as `raw` and otherwise ignored.

## Servo 2040 → Pi

### `s`: sample, 50 Hz

```json
{"k":"s","t":123456,"n":812,"feet":[1,1,1,1,0,1],"a":2.31,"v":5.98}
```

| Field | Meaning |
| --- | --- |
| `k` | Message kind. `s` = sample |
| `t` | Servo 2040 time in ms since boot (`time.ticks_ms()`). Used for intervals only |
| `n` | Sequence number, +1 per sample. A gap means the Pi dropped lines |
| `feet` | Foot switches in the order **FL, ML, RL, FR, MR, RR** (sensor headers 1–6). `1` = foot down (switch closed, ~3.3 V), `0` = foot up |
| `a` | Servo-rail current in amps |
| `v` | Servo-rail voltage in volts |

### `f`: foot change, sent immediately

```json
{"k":"f","t":123470,"leg":"ML","down":0}
```

Sent the moment a debounced switch changes (debounce ~20 ms), between samples. The flinch / landing logic can react to this without waiting for the next sample.

### `w`: warning

```json
{"k":"w","t":123500,"msg":"overcurrent","a":9.4}
```

Values for `msg`: `overcurrent` (above ~8 A, under the 10 A terminal limit), `undervolt` (rail below ~5.5 V, a brownout or flat LiPo). The Servo 2040 decides what to do itself (for example, go limp); the message tells the Pi it happened.

### `hello`: on boot

```json
{"k":"hello","fw":"body_link 0.1","feet":"FL,ML,RL,FR,MR,RR"}
```

## Pi → Servo 2040

Same format, one JSON object per line.

| Message | Meaning |
| --- | --- |
| `{"k":"rate","hz":50}` | Change the sample rate (10–100 Hz) |
| `{"k":"pose","name":"stand"}` | Run a named pose (`crouch`, `stand`, `limp`) |
| `{"k":"limp"}` | Disable all servos now |
| `{"k":"ping"}` | Servo 2040 answers `{"k":"pong","t":...}`. The Pi uses the round trip to line up the two clocks |

## Timestamps

The Pi stamps every line it receives with its own `time.monotonic()` (and wall-clock time for the log file name). **The Pi's stamp is the one used for the dataset**, so feet, current, IMU and touch all share one clock. The Servo 2040's `t` is kept for exact intervals between its own samples. USB adds about 1–2 ms, which is small next to 50 Hz (20 ms).

## Servo 2040 side: notes for the code

- Foot switches go through the board's analog mux: `servo2040.SENSOR_1_ADDR` … `SENSOR_6_ADDR`. Set a **pull-down** on each channel (`mux.configure_pull(addr, Pin.PULL_DOWN)`), or an open switch floats. Read as analog and threshold at ~1.6 V, or read digitally.
- Current and voltage come from the same mux (`CURRENT_SENSE_ADDR`, `VOLTAGE_SENSE_ADDR`) with the gain, shunt and offset constants in the `servo2040` module, as in Pimoroni's `read_current.py` / `read_voltage.py` examples.
- This needs a resident `main.py` on the Servo 2040 that loops: read sensors → send `s` → check for Pi commands → move servos. The current scripts (`stand_up.py` etc.) run one at a time, so their poses move into `main.py` as named poses.
- Keep the loop non-blocking: no long `time.sleep` inside a pose ramp, or samples stop while the legs move.

## Pi side: notes for the code

- `pyserial`, 115200 baud (USB CDC ignores the number, but set it anyway).
- One reader thread: read line → stamp → parse → append to the session log (`data/<date>/<session>.jsonl`) → hand `f` messages to the reflex code.
- Reconnect if `/dev/ttyACM0` disappears (the Servo 2040 resets when its USB power blips).

## Open questions

- Sample rate: 50 Hz matches Exp 02's 20 Hz IMU comfortably; raise it if events like a quick lift are missed.
- Whether the IMU should be logged at 50 Hz too, so all streams share a rate.
