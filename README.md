# planning_factory

**Kairos family — Brother 3: Plan**

Generates a concrete action sequence given a classified intent and current state.
Sits between `intent_factory` (what the agent intends) and `sensory_architecture_factory`
(whether the human is ready to receive the plan).

## What it does

Takes an intent label + sensor snapshot and returns a PLANNED sequence of
target values — one per time step, covering `dt_ahead` seconds into the future.

| Label | Meaning |
|---|---|
| OBSERVED | Raw input (power, gradient, fatigue) |
| PLANNED | Target power sequence — suggestions, never commands |

**All plans are `observe_only=True`.** The plan is a suggestion. The consumer
decides whether and how to act on it.

## Instances

| Instance | Domain | Input | Output |
|---|---|---|---|
| cycling | Competitive cycling | intent + power_w + ftp_w + gradient_pct + fatigue | PLANNED watt targets × N steps |

## Family position

```
perception_factory → intent_factory → planning_factory → sensory_architecture_factory
 (what is moving)    (what is intended)  (what to do)      (is the human ready)
```

## Quick start

```python
from core.planner import PacingPlanner

planner = PacingPlanner(dt=1.0)
plan = planner.plan(
    intent="ATTACK",
    power_w=255, ftp_w=300,
    gradient_pct=5.0, fatigue=0.2,
    steps=30,
)
print(plan.targets_w[:5])   # [255.0, 263.5, 272.0, 330.0, 330.0, ...]
print(plan.dt_ahead)        # 30.0 seconds
print(plan.observe_only)    # True — always
print(plan.confidence)      # "PLANNED"
```

## Tests

```
pytest instances/cycling/tests/
```

9 tests, all passing. Verified findings in `instances/cycling/NOTES.md`.

## Guardrail 8 — latency budget
`plan.dt_ahead` exposes how many seconds the plan covers.
Consumers must compare it against their event horizon before acting.
