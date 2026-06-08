# solidworks-draw

> An AI **skill** that drives SolidWorks to build parametric mechanical parts from natural language.

`solidworks-draw` lets an AI agent understand a mechanical design described in plain language
(e.g. *"draw a stepped transmission shaft, Ø30, 200 mm, with two keyways"*), reason about the
missing parameters using built-in engineering rules, confirm them with you, and then generate the
SolidWorks Python API calls that build the model.

It is packaged as an [Agent Skill](https://docs.claude.com/en/docs/agents-and-tools/agent-skills)
(`SKILL.md` + supporting knowledge/templates/utilities) and works with Claude Code, Codex, and any
agent runtime that loads skills from a skills directory.

> **Note on language:** the skill prompt (`SKILL.md`) and engineering knowledge base are written in
> Chinese, and default to GB (Chinese national) standards. This README is the English introduction.

---

## What it does

1. **Intent parsing** — extracts part type, key dimensions, material, machining features, and
   tolerance requirements from a natural-language request.
2. **Triple knowledge retrieval** — cross-checks three sources, in priority order:
   - **Learned parts library** (`knowledge/learned_parts/`) — parts extracted from your *own*
     SolidWorks files, so new designs stay consistent with your existing work.
   - **Design rules** (`knowledge/design_rules.yaml`) — empirical formulas and parameter
     relationships for shafts, pistons, flanges, gears, and general practice.
   - **Material database** (`knowledge/material_db.yaml`) — properties, applications, and
     heat-treatment notes for common engineering materials.
3. **Parameter inference** — derives any unspecified parameters and **explains the source of each**
   (standard, learned part, or design rule).
4. **Confirmation** — prints a full parameter table and waits for your approval before generating
   any code.
5. **Execution** — calls the matching template to emit a complete SolidWorks Python script.

```
Natural language → intent parsing → triple knowledge retrieval → parameter inference → confirm → execute
```

---

## Features

- 🗣️ **Natural-language modeling** — describe the part, not the API.
- 📐 **Engineering-aware** — built-in GB-standard design rules and a material database.
- 🧠 **Learns from your files** — `sw_extractor.py` turns existing `.sldprt` files into a
  structured knowledge base; the more parts it learns, the closer its output matches your
  shop's conventions.
- 🔍 **Similarity search** — finds the closest existing parts to use as a reference for a new design.
- ✅ **Confirm-before-build** — never silently guesses; every derived value is justified.
- 💾 **Offline-safe** — if SolidWorks is not installed, scripts emit a JSON description instead.

---

## Supported parts

| Category | Template | Status | Typical features |
|----------|----------|--------|------------------|
| Shaft (transmission / stepped) | `templates/shaft.py` | ✅ Implemented | multi-section cylinders, keyways, retaining-ring grooves, center holes, threads |
| Piston | `templates/piston.py` | ✅ Implemented | piston body, ring grooves, pin bore, skirt, relief grooves |
| Flange | — | 📋 Design rules only | disc, bolt-hole pattern, center bore, seal groove |
| Gear | — | 📋 Design rules only | tooth profile, hub, keyway, lightening holes |

Flange and gear have engineering rules in `design_rules.yaml` but no code template yet —
contributions welcome.

---

## Repository layout

```
solidworks-draw/
├── SKILL.md                       ← skill prompt (Chinese) — the agent entry point
├── knowledge/
│   ├── design_rules.yaml          ← engineering design rules (shaft/piston/flange/gear/general)
│   ├── material_db.yaml           ← material properties (steels, stainless, cast iron, Al, Cu, plastics)
│   └── learned_parts/             ← parts learned from your SolidWorks files
│       ├── README.md
│       └── example_shaft_d30.json ← sample extraction result
├── templates/
│   ├── shaft.py                   ← shaft generator
│   └── piston.py                  ← piston generator
├── utils/
│   ├── sw_api.py                  ← SolidWorks COM API wrapper
│   ├── sw_extractor.py            ← extracts knowledge from .sldprt files
│   └── similarity.py              ← similar-part search engine
├── LICENSE
└── README.md
```

---

## Requirements

- **SolidWorks** installed on Windows (uses the `SldWorks.Application` COM API) — only needed to
  actually build/extract models; the skill can still reason and emit JSON without it.
- **Python 3.10+**
- `pywin32` (for the COM bridge) when running against a live SolidWorks instance.

---

## Installation

Place the `solidworks-draw/` folder in your agent's skills directory, e.g.:

| Runtime | Path |
|---------|------|
| Claude Code | `~/.claude/skills/solidworks-draw/` |
| Codex | `~/.codex/skills/solidworks-draw/` |

The agent discovers the skill via `SKILL.md` and invokes it on prompts like *"画一个…"* / *"draw a…"* /
*"help me model…"*.

---

## Usage

### Build a part from natural language

Just ask the agent:

> 画一个直径30、长200的传动轴，两端各一个键槽
> *(Draw a Ø30 × 200 transmission shaft with a keyway at each end.)*

The agent retrieves references, infers the missing parameters, shows a confirmation table, and on
approval generates the SolidWorks script.

### Teach it from your existing files (training mode)

```bash
# Extract knowledge from a single file
python utils/sw_extractor.py -i "D:/CAD/my_shaft.sldprt" -o knowledge/learned_parts/

# Or batch-extract an entire project
python utils/sw_extractor.py -i "D:/CAD/ProjectX/" -o knowledge/learned_parts/ --batch

# Search for similar reference parts
python utils/similarity.py --type shaft --dims diameter=30 length=200
```

| Learned samples | Behavior |
|-----------------|----------|
| 0 | Generic textbook design rules |
| 5–10 | Learns your material preferences and size ranges |
| 20–50 | Learns your company's design conventions |
| 100+ | Closely matches your design habits; can flag anomalies |

> **Privacy:** this public repository contains **only** a sample part
> (`example_shaft_d30.json`). No proprietary/learned part data is included. Anything you extract
> into `learned_parts/` stays local unless you choose to commit it.

---

## Defaults

| Item | Default |
|------|---------|
| Units | millimeters (mm) |
| Angles | degrees (°) |
| Standards | GB (Chinese national standards) |
| Default material | 45 steel |
| Surface roughness | Ra 3.2 |
| Thread standard | Metric M series (coarse) |
| Tolerance grade | IT7 (bearing fits), IT12 (non-mating) |

---

## Contributing & Contact

Feedback and contributions are welcome! If you'd like to discuss improvements, share design
rules, contribute new part templates, or help optimize this skill, feel free to reach out:

📧 **2106105507@qq.com**

---

## License

[MIT](LICENSE) © 2026 SHY-563
