# krēCHer

**A small Linux computer with a body.** krēCHer is a soft, furry hexapod creature built around a Raspberry Pi 5. It senses the physical world (touch, movement, sight and sound), reacts to it with its body, and will eventually let a remote person see through its eyes and move its head.

> Fall 2026 · PSAM 5600 B *Currents: Small Devices, Large Language Models* (Prof. David Carroll) · PGTE 5900 Independent Study (Prof. Thiago Hersan) · Parsons / The New School

**SENSE → COMPUTE → REACT → CONNECT → REMOTE PRESENCE**

## Where it is now (Oct 1, 2026)

| Part | Status |
| --- | --- |
| **Head** | Assembled and working: Pi 5 + SunFounder Fusion HAT+, pan-tilt camera, speaker and mic, own 2S battery |
| **Touch** (Exp. 01) | Done: lever micro-switches read reliably by the Pi |
| **Movement** (Exp. 02) | Done: BNO085 motion sensor logged (1,500 readings, 0 errors), and **the head follows the sensor in real time** |
| **Body** | Hexapod frame, 20 MG996R servos (18 + 2 spares), **all 20 bench-tested and passing** ([test guide](body/servo_test/)), Servo 2040 leg controller running on USB. Build in progress |
| **Networking** | The Pi opens a tunnel on boot, so I can reach it from anywhere; works on a phone hotspot in class |
| **Language model** | The Pi asks a model on the class GPU box over Tailscale and gets a reply in 0.35 s ("Ouch!") |

## How it fits together

- **Reflexes run on the Pi**, straight from the sensors, with no network and no model: the flinch, the head following its own movement.
- **Voice and face reactions** come from a language model (gemma4:e4b) on a GPU box from the class lab, reached over Tailscale. If the box is slow or offline, krēCHer plays a canned reaction instead of freezing.
- **Two power systems:** the head runs on its own 2S battery; the legs run on a 3S LiPo through a buck converter set to 6 V.

Diagrams and details: [`docs/system_map.md`](docs/system_map.md).

## Repo map

| Path | What's there |
| --- | --- |
| [`exp01/`](exp01/) | Experiment 01, touch sensing: scripts, wiring diagrams, logs, [report](exp01/REPORT.md) |
| [`exp02/`](exp02/) | Experiment 02, movement sensing: IMU reader, logger, head-follow script, logged trial, [report](exp02/REPORT.md) |
| [`head/`](head/) | Pan-tilt servo centring and test |
| [`body/`](body/) | Hexapod body build: [servo bench test](body/servo_test/) (wiring, steps, photos, results) |
| [`system/`](system/) | systemd tunnel service and the relay node's SSH keep-alive config |
| [`docs/`](docs/) | [System map](docs/system_map.md) · [Model speed and quality tests](docs/model_benchmarks.md) · [Hardware BOM](docs/bom.md) |
| [`notes/`](notes/) | Dated setup logs (what was done, what broke, what was decided) and head hardware notes |

## Try the head-follow demo

On the Pi, with the BNO085 plugged into the Fusion HAT+'s I2C port:

```
cd ~/krecher && git pull
source ~/venvs/imu/bin/activate
python3 exp02/imu_head_follow.py
```

Hold the sensor flat and still while it starts (that pose becomes "home"), then tilt and turn it: the camera head follows. Ctrl+C centres the head and exits.

## Road to the final demo (Nov 18)

1. **Oct 7 · Midterm pitch:** head demo + walkthrough of this repo; body assembly under way.
2. **Body stands:** all 18 servos in the frame, foot-contact switches in all six feet.
3. **Tripod gait:** walking, with a go / no-go at the Oct 28 crit (fallback: standing and single-leg moves).
4. **Skin:** foam and fur on, kept light.
5. **Remote presence:** a remote person sees through the camera and moves the head.
6. **Independent study:** detect higher-level events from the sensors (picked up, shaken, touched, approached) and compare running that on the Pi vs a server.

## How this is made

I write krēCHer's code with Claude as a coding partner; commits that came out of those sessions carry a `Co-Authored-By: Claude` trailer. Local models on the class GPU box are tested and compared in [`docs/model_benchmarks.md`](docs/model_benchmarks.md).

## Credits and license

Sources are listed in [`BIBLIOGRAPHY.md`](BIBLIOGRAPHY.md). Code is released under the [MIT License](LICENSE). Please read the [Code of Conduct](CODE_OF_CONDUCT.md) before opening an issue or contributing.

## Safety notes

- Never connect the 3S LiPo (or its charger) to the Fusion HAT+. The HAT takes only its own 2S battery or USB-C.
- Set and measure the buck converter's output before any servo is connected.
- LiPos are charged in a fireproof bag, never unattended, and stored at ~3.8 V per cell.
