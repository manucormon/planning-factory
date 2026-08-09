"""
Pacing planner — generates a target power sequence given a classified intent.

Input:  IntentLabel (ATTACK | MAINTAIN | RECOVER) + current sensor state
Output: PacingPlan — N target power values (watts), one per step

Confidence vocabulary:
  OBSERVED — raw input (power_w, gradient_pct, fatigue)
  PLANNED  — output power targets (suggestions, never commands)

IMPORTANT: PacingPlan.observe_only is always True.
The planner produces suggestions. Actuation is the athlete's / consumer's decision.
This is not negotiable — it is a family invariant (CONTRACT_FAMILY.md, Invariant 4).

Planning logic (all targets DECLARED):

  ATTACK:
    target_ratio = min(ATTACK_CEILING, 1.05 + (1 - fatigue) * FATIGUE_SCALE)
    gradient_penalty: each % grade above GRADIENT_PIVOT reduces target by GRADIENT_RATE
    ramp: linear from current_ratio → target over first RAMP_FRAC of steps, then hold

  MAINTAIN:
    target_ratio = clip(current_ratio + gradient_pct * GRADIENT_HOLD_ADJ, HOLD_LO, HOLD_HI)
    flat: hold that target for all steps

  RECOVER:
    target_ratio = RECOVER_TARGET
    decay: linear from current_ratio → target over DECAY_FRAC of steps, then hold

Constants:
  ATTACK_CEILING  = 1.15   (115% FTP — max sustainable attack in this model)
  FATIGUE_SCALE   = 0.15   (at fatigue=0, ceiling is 1.20; at fatigue=1, floored at 1.05)
  GRADIENT_PIVOT  = 5.0    (% grade above which gradient penalizes attack target)
  GRADIENT_RATE   = 0.010  (each % grade above pivot reduces target ratio by 1%)
  ATTACK_FLOOR    = 1.05   (minimum attack target even on steep grades)
  HOLD_LO         = 0.56   (lower clip for MAINTAIN — just above recover zone)
  HOLD_HI         = 1.04   (upper clip for MAINTAIN — just below attack zone)
  GRADIENT_HOLD_ADJ = 0.005  (gradient smoothing: each % grade adjusts hold by 0.5%)
  RECOVER_TARGET  = 0.50   (50% FTP)
  RAMP_FRAC       = 0.33   (first 1/3 of steps used for ramp-up in ATTACK)
  DECAY_FRAC      = 0.25   (first 1/4 of steps used for decay in RECOVER)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Literal

IntentLabel = Literal["ATTACK", "MAINTAIN", "RECOVER"]

# --- Constants (DECLARED) ---------------------------------------------------
_ATTACK_CEILING    = 1.15
_FATIGUE_SCALE     = 0.15
_GRADIENT_PIVOT    = 5.0
_GRADIENT_RATE     = 0.010
_ATTACK_FLOOR      = 1.05
_HOLD_LO           = 0.56
_HOLD_HI           = 1.04
_GRADIENT_HOLD_ADJ = 0.005
_RECOVER_TARGET    = 0.50
_RAMP_FRAC         = 0.33
_DECAY_FRAC        = 0.25


@dataclass
class PacingPlan:
    intent: str                 # the IntentLabel that generated this plan
    steps: int
    targets_w: List[float]      # PLANNED target power in watts, one per step
    dt_ahead: float             # seconds this plan covers
    observe_only: bool = True   # always True — plan is suggestion, not command
    confidence: str = "PLANNED"


class PacingPlanner:
    """
    Stateless pacing planner. Each call to plan() is independent.

    dt: seconds between steps (used to compute dt_ahead).
    """

    def __init__(self, dt: float = 1.0):
        if dt <= 0 or not math.isfinite(dt):
            raise ValueError(f"dt must be positive and finite, got {dt}")
        self.dt = dt

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def plan(
        self,
        intent: IntentLabel,
        power_w: float,
        ftp_w: float,
        gradient_pct: float = 0.0,
        fatigue: float = 0.0,
        steps: int = 30,
    ) -> PacingPlan:
        """
        Generate a PLANNED power sequence for the given intent and state.
        Returns a PacingPlan with observe_only=True (suggestions only).
        """
        self._validate(intent, power_w, ftp_w, gradient_pct, fatigue, steps)

        current_ratio = power_w / ftp_w

        if intent == "ATTACK":
            targets_ratio = self._attack_targets(
                current_ratio, gradient_pct, fatigue, steps
            )
        elif intent == "RECOVER":
            targets_ratio = self._recover_targets(current_ratio, steps)
        elif intent == "MAINTAIN":
            targets_ratio = self._maintain_targets(
                current_ratio, gradient_pct, steps
            )
        else:
            raise ValueError(f"Unknown intent: {intent!r}")

        return PacingPlan(
            intent=intent,
            steps=steps,
            targets_w=[round(r * ftp_w, 1) for r in targets_ratio],
            dt_ahead=steps * self.dt,
        )

    # ------------------------------------------------------------------
    # Internal — one method per intent
    # ------------------------------------------------------------------

    def _attack_targets(
        self,
        current_ratio: float,
        gradient_pct: float,
        fatigue: float,
        steps: int,
    ) -> List[float]:
        target = min(_ATTACK_CEILING, 1.05 + (1.0 - fatigue) * _FATIGUE_SCALE)
        gradient_penalty = max(0.0, gradient_pct - _GRADIENT_PIVOT) * _GRADIENT_RATE
        target = max(_ATTACK_FLOOR, target - gradient_penalty)

        ramp_steps = max(1, int(steps * _RAMP_FRAC))
        return _linear_ramp(current_ratio, target, ramp_steps, steps)

    def _recover_targets(
        self,
        current_ratio: float,
        steps: int,
    ) -> List[float]:
        decay_steps = max(1, int(steps * _DECAY_FRAC))
        return _linear_ramp(current_ratio, _RECOVER_TARGET, decay_steps, steps)

    def _maintain_targets(
        self,
        current_ratio: float,
        gradient_pct: float,
        steps: int,
    ) -> List[float]:
        adj = gradient_pct * _GRADIENT_HOLD_ADJ
        target = min(_HOLD_HI, max(_HOLD_LO, current_ratio + adj))
        return [target] * steps

    # ------------------------------------------------------------------

    @staticmethod
    def _validate(
        intent: str,
        power_w: float,
        ftp_w: float,
        gradient_pct: float,
        fatigue: float,
        steps: int,
    ) -> None:
        if intent not in ("ATTACK", "MAINTAIN", "RECOVER"):
            raise ValueError(f"intent must be ATTACK/MAINTAIN/RECOVER, got {intent!r}")
        if not math.isfinite(power_w) or power_w < 0:
            raise ValueError(f"power_w must be finite and ≥ 0, got {power_w}")
        if not math.isfinite(ftp_w) or ftp_w <= 0:
            raise ValueError(f"ftp_w must be finite and > 0, got {ftp_w}")
        if not math.isfinite(gradient_pct) or not (-20.0 <= gradient_pct <= 20.0):
            raise ValueError(f"gradient_pct must be in [-20, 20], got {gradient_pct}")
        if not math.isfinite(fatigue) or not (0.0 <= fatigue <= 1.0):
            raise ValueError(f"fatigue must be in [0, 1], got {fatigue}")
        if steps <= 0:
            raise ValueError(f"steps must be > 0, got {steps}")


def _linear_ramp(
    start: float, end: float, ramp_steps: int, total_steps: int
) -> List[float]:
    """Linearly interpolate from start → end over ramp_steps, then hold end."""
    result = []
    for i in range(total_steps):
        if i < ramp_steps:
            t = i / ramp_steps
            result.append(start + t * (end - start))
        else:
            result.append(end)
    return result
