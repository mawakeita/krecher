# Language models: speed and quality tests

As of Oct 1, 2026. How fast different machines run local language models with Ollama, how well they write a small creature sketch, and how quickly krēCHer's Pi can get a reply from the class GPU box.

## Speed

| Machine | Model | Speed | Source |
|---|---|---|---|
| MacBook Air M1, 8 GB | llama3.2 3B | ~23 tok/s | my test, Sep 22 |
| Oracle node (aarch64, 4 cores, 23 GB, CPU only) | llama3.2 3B | ~12.5 tok/s | my test, Sep 22 |
| D12 box 1 (Ryzen 9800X3D, RTX 5070 Ti) | gemma4:e4b | 168 tok/s | class repo dossier |
| D12 box 2 `d12-node-flux` (RTX 5080) | gemma4:e4b | 182 tok/s | class repo dossier |
| D12 `d12-node-mosiac` (RTX 2070 SUPER 8 GB) | 4B–9B models | 58–86 tok/s | class repo dossier |
| **My checkout `d12-compute` (RTX 5070 Ti 16 GB)** | gemma4:e4b | **~158 tok/s** | my test, Sep 30 |
| same | qwen3-coder:30b (18 GB) | **~67–71 tok/s** | my test, Sep 30 / Oct 1 |
| same | gpt-oss:20b (13 GB) | **~164–170 tok/s** | my test, Sep 30 / Oct 1 |

- **gpt-oss:20b is the fastest** despite being bigger than e4b: it's a mixture-of-experts model that only uses a few billion parameters per token, and at 13 GB it fits fully on the 16 GB card.
- **qwen3-coder:30b is ~2.5× slower** because at 18 GB it doesn't fit on the card; part runs on the CPU. Still ~3× my Mac.
- The checkout listing calls this machine "Box 2", but its speed matches the dossier's 5070 Ti figure.
- gemma4:e4b and gpt-oss "think" before answering on some prompts; the thinking tokens add to response time.
- **Self-identification is unreliable:** qwen3-coder said it was made by Anthropic (it's Alibaba's Qwen); gpt-oss said it was ChatGPT (it's OpenAI's open-weight model). A model's description of itself isn't a fact.

## Quality: the flinch sketch

Original prompt: "Write a p5.js sketch of a creature that flinches when the mouse touches it."

Detailed prompt: "a soft round creature with eyes; when the mouse moves over its body (no click) it flinches: jerks away from the cursor and squints for about half a second, then slowly relaxes back to its resting spot; it must stay fully on the canvas; return one complete sketch.js file."

Earlier, on 3B models:
- Mac: code ran, but the creature was a red square that twitched and drifted, and any click triggered the flinch.
- Oracle node: code ran, but the flinch never ended (the timer reset every frame), it drifted off the canvas, and it reacted to clicks only.

On the D12 box (Oct 1). The two detailed sketches were run in the p5.js editor; the original-prompt rows come from reading the code.

| Model · prompt | Speed / time | Creature? | Hover, not click? | Flinch ends? | On canvas? | Main problem |
|---|---|---|---|---|---|---|
| qwen3-coder:30b · original | 68.7 tok/s, 17.9 s | Yes (body, head, eyes, spinning legs) | Yes | Only when the mouse leaves | Yes | "Flinch" = it gets bigger; it doesn't recoil |
| qwen3-coder:30b · detailed | 66.7 tok/s, 20.1 s | Yes (pink, eyes, smile) | Yes | Yes; home within ~3 s | Yes | Squint lines never clear after the first flinch; small hop (~30 px); can overshoot home if the cursor sits near its centre |
| gpt-oss:20b · original | 167.2 tok/s, 9.8 s | No (8 plain circles) | Yes | Yes, but never returns home | Mostly | Not a creature |
| gpt-oss:20b · detailed | 163.9 tok/s, 17.5 s | Yes (blue, eyes) | Yes | Recoil ends after 0.5 s | Yes | Drifts home at ~3 px/s (~80 s); "squint" is tiny pupils |

- **Closest to the brief:** qwen3-coder with the detailed prompt. Two one-line fixes make it right: reset the squint when not flinching, and clamp the return progress with `constrain(..., 0, 1)`.
- **gpt-oss fix:** raise the return speed (`dir.setMag(0.05)` → about `2`).
- **The detailed prompt helped both models a lot.** Both now recoil from the cursor and stay on canvas, a big jump over the 3B models.
- gpt-oss writes ~2.5× faster per token but spends many tokens thinking first, so total time was similar (17.5 s vs 20.1 s).
- **Gotcha:** `ollama run` breaks long lines when it prints, and copied code keeps those breaks (one turned a comment into a syntax error). Use `ollama run <model> --nowordwrap` for code.

## Pi → GPU box (Oct 1)

The Pi (on the hotspot, the demo network) asked gemma4:e4b on the box over Tailscale. Prompt: "You are a small creature. Someone just poked you. Say one short sentence." (`think:false`). Reply every time: **"Ouch!"**

| Run | Time on the box | Loading | Round trip from the Pi |
|---|---|---|---|
| 1st (cold) | 2.17 s | most of it | — |
| 2nd (warm) | 0.06 s | 0.00 s | — |
| 3rd (warm) | 0.056 s | 0.0006 s | **0.35 s** |

- **Cold start costs ~2 s:** Ollama unloads a model after ~5 min idle or when another model is used. Fix: a warm-up request at startup, and `"keep_alive":"30m"` on requests.
- **Warm: 0.35 s from poke to answer**, of which the model is only ~0.06 s. The rest is the network: on the hotspot, Tailscale can't make a direct link and goes through a relay (64–356 ms per ping).
- Fast enough for spoken or facial reactions. Too slow, and too dependent on Wi-Fi, for the flinch reflex, which stays on the Pi.
- Design numbers for the demo: expect ~0.3–0.4 s per short reply with occasional spikes; time out after ~2 s and fall back to a canned reaction.

## What it means for krēCHer

See [`system_map.md`](system_map.md) §4: reflexes on the Pi with no model; voice and face reactions from gemma4:e4b on a checked-out D12 box, with a canned fallback; code written by me with Claude, with qwen3-coder as something to try and compare.
