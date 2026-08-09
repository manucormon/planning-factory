# NOTES — cycling instance

**Status:** verified
**Data:** DECLARED (threshold-based planner)

## Data provenance

| Variable | Label | Source |
|---|---|---|
| power_w, gradient_pct, fatigue | OBSERVED | caller-provided sensor state |
| intent | OBSERVED | output of `intent_factory` cycling classifier |
| targets_w | PLANNED | `core/planner.py` — threshold + ramp/decay logic |

## Verified findings

1. **Gradient modulates ATTACK ceiling:** each % grade above 5% reduces the
   target ratio by 1% FTP. At 14% grade vs 2% grade, the final ATTACK target
   differs measurably. Rationale: steep gradient limits biomechanical power output.

2. **Fatigue modulates ATTACK ceiling:** target = min(1.15, 1.05 + (1-fatigue)×0.15).
   Fresh athlete (fatigue=0.10) → ceiling ~1.19. Tired athlete (fatigue=0.80) → ceiling ~1.08.

3. **Ramp/decay transitions are smooth:** ATTACK ramps over first 1/3 of steps;
   RECOVER decays over first 1/4 of steps. Avoids abrupt power spikes in the plan.

4. **observe_only is always True.** The plan is a suggestion — the athlete
   (or the consumer system) decides whether to follow it. This is a family
   invariant and cannot be overridden by the caller.

## Connection to the family

```
perception_factory → intent_factory → planning_factory → sensory_architecture_factory
  TRACKED position    CLASSIFIED       PLANNED targets     Governs whether to deliver
  velocity, accel     ATTACK intent    [330W, 335W, ...]   the plan to the athlete
```

The `sensory_architecture_factory` cycling instance decides whether the athlete
has enough cognitive bandwidth to receive and act on the plan. If load is too high,
the plan is held back — the planner produced it, but the governor withholds it.
