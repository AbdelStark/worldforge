"""Stable facade for built-in deterministic evaluation suite implementations."""

from __future__ import annotations

from worldforge.evaluation.physics_suite import PhysicsEvaluationSuite
from worldforge.evaluation.planning_suite import PlanningEvaluationSuite

__all__ = [
    "PhysicsEvaluationSuite",
    "PlanningEvaluationSuite",
]
