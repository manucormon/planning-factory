# CONTRACT.md — planning_factory

Part of the Kairos family. See `kairos-factory/CONTRACT_FAMILY.md` for shared invariants.

## Brother identity
- **Position:** Brother 3 — Plan
- **Time axis:** near-future action sequence (what to do over the next N steps)
- **Facing:** World-facing (generates a plan for the physical world)

## Family invariants satisfied

| Invariant | How |
|---|---|
| Confidence vocabulary | OBSERVED / PLANNED — in every output |
| Latency exposed | `plan.dt_ahead` on every PacingPlan |
| Verified finding | Gradient and fatigue modulation verified in tests; NOTES.md |
| No full autonomy | `observe_only=True` is hardcoded — the planner never commands |
| CONTRACT.md gated | This file |
| Scope discipline | Does not classify intent, does not govern attention |

## What this brother does NOT decide
- Does not decide what the intent is (that is `intent_factory`)
- Does not assess whether the human can receive the plan (that is `sensory_architecture_factory`)
- Does not execute the plan — output is always a suggestion
