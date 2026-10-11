"""
[DEPRECATED] Risk scoring engine for the AI Ingredient Intelligence Engine.

Deprecated in Phase 1: Consolidated into app.services.risk_engine.ProductRiskEngine.
This class delegates to ProductRiskEngine to preserve backward compatibility for legacy imports.
"""

from __future__ import annotations

import warnings
from app.schemas.analysis import OverallAnalysis
from app.services.risk_engine import ProductRiskEngine


class RiskEngine:
    """[DEPRECATED] Legacy risk engine interface.

    Delegates calculation methods to the authoritative :class:`ProductRiskEngine`.
    """

    def __init__(self) -> None:
        warnings.warn(
            "app.services.analysis.risk_engine.RiskEngine is deprecated. "
            "Use app.services.risk_engine.ProductRiskEngine instead.",
            DeprecationWarning,
            stacklevel=2,
        )

    @staticmethod
    def calculate_overall_score(safety_ratings: list[float]) -> float:
        """Compute aggregate safety score (delegated to ProductRiskEngine)."""
        return ProductRiskEngine.calculate_overall_score(safety_ratings)

    @staticmethod
    def calculate_risk_level(score: float) -> str:
        """Classify safety score into risk level (delegated to ProductRiskEngine)."""
        return ProductRiskEngine.calculate_risk_level(score)

    def analyze(
        self,
        safety_ratings: list[float],
    ) -> OverallAnalysis:
        """Run legacy deterministic scoring pipeline."""
        score = self.calculate_overall_score(safety_ratings)
        risk = self.calculate_risk_level(score)

        return OverallAnalysis(
            overall_score=score,
            overall_risk=risk,
            ingredient_count=len(safety_ratings),
            summary="",
            recommendations=[],
        )


