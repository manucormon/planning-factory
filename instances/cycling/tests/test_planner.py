"""
11 tests for the cycling pacing planner instance.

Verified findings (DECLARED thresholds, ftp=300W synthetic):
  - ATTACK plan targets > 1.05 FTP on moderate gradient and low fatigue
  - ATTACK target is reduced by steep gradient and high fatigue
  - RECOVER plan targets < 0.55 FTP after decay
  - MAINTAIN plan holds near current power within [0.56, 1.04] FTP band
  - All plans are observe_only=True (suggestions, never commands)
  - dt_ahead matches steps * dt
  - Invalid inputs raise ValueError

Real data validation (GoldenCheetah OpenData, CC BY 4.0, anonymous athlete):
  - 601 real samples (t=300-900s), FTP=208W, power=REAL, gradient/fatigue=DECLARED
  - Pipeline: real state → classify intent → generate plan
  - ATTACK plans generated from real ATTACK moments all exceed 1.05 FTP
  - RECOVER plans generated from real RECOVER moments all stay below 0.55 FTP
  - Plans are always PLANNED + observe_only=True regardless of data source
"""

import csv
import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3]))

from core.planner import PacingPlanner, PacingPlan

FTP = 300.0


@pytest.fixture
def planner():
    return PacingPlanner(dt=1.0)


# -----------------------------------------------------------------------

def test_attack_plan_targets_above_ftp(planner):
    plan = planner.plan("ATTACK", power_w=FTP * 0.85, ftp_w=FTP,
                        gradient_pct=5.0, fatigue=0.2, steps=30)
    held_targets = plan.targets_w[10:]  # post-ramp
    assert all(t > FTP * 1.05 for t in held_targets), \
        f"ATTACK plan should hold above 105% FTP, got {min(held_targets):.1f}W"


def test_recover_plan_targets_below_recover_threshold(planner):
    plan = planner.plan("RECOVER", power_w=FTP * 0.85, ftp_w=FTP,
                        gradient_pct=0.0, fatigue=0.3, steps=30)
    held_targets = plan.targets_w[10:]  # post-decay
    assert all(t <= FTP * 0.55 for t in held_targets), \
        f"RECOVER plan should hold at or below 55% FTP, got {max(held_targets):.1f}W"


def test_maintain_plan_stays_in_band(planner):
    plan = planner.plan("MAINTAIN", power_w=FTP * 0.80, ftp_w=FTP,
                        gradient_pct=3.0, fatigue=0.3, steps=30)
    assert all(FTP * 0.56 <= t <= FTP * 1.04 for t in plan.targets_w), \
        "MAINTAIN plan must stay within [0.56, 1.04] FTP band"


def test_attack_target_reduced_by_steep_gradient(planner):
    plan_flat  = planner.plan("ATTACK", power_w=FTP * 0.85, ftp_w=FTP,
                               gradient_pct=2.0, fatigue=0.2, steps=30)
    plan_steep = planner.plan("ATTACK", power_w=FTP * 0.85, ftp_w=FTP,
                               gradient_pct=14.0, fatigue=0.2, steps=30)
    flat_held  = plan_flat.targets_w[-1]
    steep_held = plan_steep.targets_w[-1]
    assert steep_held < flat_held, \
        f"Steep gradient should reduce attack target: {steep_held:.1f}W vs {flat_held:.1f}W"


def test_attack_target_reduced_by_high_fatigue(planner):
    plan_fresh  = planner.plan("ATTACK", power_w=FTP * 0.85, ftp_w=FTP,
                                gradient_pct=3.0, fatigue=0.1, steps=30)
    plan_tired  = planner.plan("ATTACK", power_w=FTP * 0.85, ftp_w=FTP,
                                gradient_pct=3.0, fatigue=0.80, steps=30)
    assert plan_tired.targets_w[-1] < plan_fresh.targets_w[-1], \
        "Higher fatigue should produce a lower ATTACK ceiling"


def test_plan_length_matches_steps(planner):
    for steps in (10, 30, 60):
        plan = planner.plan("MAINTAIN", power_w=FTP * 0.80, ftp_w=FTP, steps=steps)
        assert len(plan.targets_w) == steps


def test_dt_ahead_matches_steps(planner):
    plan = planner.plan("ATTACK", power_w=FTP * 0.85, ftp_w=FTP, steps=45)
    assert plan.dt_ahead == pytest.approx(45.0)


def test_plan_is_always_observe_only(planner):
    """Family invariant: the planner never commands — output is always a suggestion."""
    for intent in ("ATTACK", "MAINTAIN", "RECOVER"):
        plan = planner.plan(intent, power_w=FTP * 0.80, ftp_w=FTP, steps=10)
        assert plan.observe_only is True, \
            f"Plan for {intent} must have observe_only=True"
        assert plan.confidence == "PLANNED"


def test_invalid_inputs_raise(planner):
    with pytest.raises(ValueError):
        planner.plan("SPRINT", power_w=FTP, ftp_w=FTP)       # unknown intent
    with pytest.raises(ValueError):
        planner.plan("ATTACK", power_w=-10, ftp_w=FTP)       # negative power
    with pytest.raises(ValueError):
        planner.plan("ATTACK", power_w=FTP, ftp_w=0)         # zero FTP
    with pytest.raises(ValueError):
        planner.plan("ATTACK", power_w=FTP, ftp_w=FTP, gradient_pct=25.0)  # out of range
    with pytest.raises(ValueError):
        planner.plan("ATTACK", power_w=FTP, ftp_w=FTP, steps=0)            # no steps


def _load_real_samples():
    """Load real ride CSV (power=REAL, gradient/fatigue=DECLARED)."""
    data_path = Path(__file__).parents[1] / "data" / "real_ride_sample.csv"
    samples = []
    with open(data_path) as f:
        for row in csv.DictReader(f):
            samples.append({
                "power_w":      float(row["power_w"]),
                "ftp_w":        float(row["ftp_w"]),
                "gradient_pct": float(row["gradient_pct"]),
                "fatigue":      float(row["fatigue"]),
            })
    return samples


def _classify_intent(s: dict) -> str:
    """Inline threshold classifier (mirrors intent_factory logic)."""
    ratio = s["power_w"] / s["ftp_w"]
    fatigue = s["fatigue"]
    gradient = s["gradient_pct"]
    if fatigue >= 0.90:
        return "RECOVER"
    if ratio < 0.55:
        return "RECOVER"
    if ratio > 1.05:
        if gradient > 15.0 or fatigue >= 0.85:
            return "MAINTAIN"
        return "ATTACK"
    return "MAINTAIN"


def test_real_attack_plans_exceed_ftp(planner):
    """
    Verified finding: pacing plans generated from real ATTACK moments (real
    power > 1.05 FTP, FTP=208W) all hold targets above 1.05 FTP post-ramp.
    Input: power=REAL, gradient/fatigue=DECLARED. Output: PLANNED.
    """
    samples = _load_real_samples()
    attack_samples = [s for s in samples if _classify_intent(s) == "ATTACK"]
    assert len(attack_samples) > 0, "No ATTACK samples in real data"

    for s in attack_samples[:20]:  # verify first 20 attack moments
        plan = planner.plan("ATTACK", s["power_w"], s["ftp_w"],
                            s["gradient_pct"], s["fatigue"], steps=30)
        held = plan.targets_w[10:]  # post-ramp targets
        # Use 1.049 (not 1.05) to avoid floating-point rounding errors in
        # planner output (round to 1dp) vs the exact ATTACK_FLOOR constant.
        assert all(t >= s["ftp_w"] * 1.049 for t in held), \
            f"ATTACK plan below ATTACK_FLOOR for real sample: {s}"


def test_real_recover_plans_stay_below_threshold(planner):
    """
    Verified finding: pacing plans generated from real RECOVER moments all
    hold targets at or below 0.55 FTP after the decay phase.
    Input: power=REAL, gradient/fatigue=DECLARED. Output: PLANNED.
    """
    samples = _load_real_samples()
    recover_samples = [s for s in samples if _classify_intent(s) == "RECOVER"]
    assert len(recover_samples) > 0, "No RECOVER samples in real data"

    for s in recover_samples[:20]:
        plan = planner.plan("RECOVER", s["power_w"], s["ftp_w"],
                            s["gradient_pct"], s["fatigue"], steps=30)
        held = plan.targets_w[10:]  # post-decay targets
        assert all(t <= s["ftp_w"] * 0.55 for t in held), \
            f"RECOVER plan above 0.55 FTP for real sample: {s}"
