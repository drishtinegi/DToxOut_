"""
OCR Preparation Adapter Service.

Processes raw OCR text, invokes OCR cleaning utilities, matches candidate terms
via IngredientMatcher, calculates parser confidence, and flags review requirement.
"""

from typing import Any, Dict, List, Optional
from prisma import Prisma

from app.utils.ingredient_matcher import IngredientMatcher, MatchResult, MatchType
from app.utils.ocr_cleaner import clean_ocr_raw_text


class OCRAdapter:
    """
    Adapter for vendor-independent OCR text preparation and pre-analysis validation.
    """

    def __init__(self, matcher: Optional[IngredientMatcher] = None) -> None:
        self.matcher = matcher or IngredientMatcher()

    async def prepare_ocr_text(
        self,
        raw_text: str,
        db: Optional[Prisma] = None
    ) -> Dict[str, Any]:
        """
        Prepares raw OCR text: cleans text, extracts candidate terms, evaluates match details,
        computes parser confidence, and determines review_required status.

        Does not persist scan history or run full product risk evaluation.
        """
        cleaned_text, candidate_terms, warnings = clean_ocr_raw_text(raw_text)

        if not candidate_terms:
            return {
                "raw_text": raw_text,
                "cleaned_text": cleaned_text,
                "candidate_terms": [],
                "match_details": [],
                "parser_confidence": 0.0,
                "review_required": True,
                "warnings": warnings + ["No valid ingredient candidate terms could be extracted from input text."],
                "candidate_count": 0,
                "recognized_count": 0,
                "unknown_count": 0,
            }

        # Batch match candidate terms if db provided or using loaded matcher
        if db is not None:
            await self.matcher.load_knowledge_base(db)

        match_results: List[MatchResult] = self.matcher.match_batch(candidate_terms)

        match_details = []
        recognized_count = 0
        unknown_count = 0

        for res in match_results:
            if res.match_type != MatchType.UNKNOWN:
                recognized_count += 1
            else:
                unknown_count += 1

            match_details.append({
                "candidate_term": res.query_term,
                "match_type": res.match_type.value,
                "matched_inci": res.matched_inci,
                "confidence_score": round(res.confidence_score, 2),
                "manual_confirmation_recommended": res.manual_confirmation_recommended,
                "reason": res.reason,
            })

        candidate_count = len(candidate_terms)
        recognition_ratio = (recognized_count / candidate_count) if candidate_count > 0 else 0.0

        # Calculate parser confidence (0-100 scale)
        parser_confidence = recognition_ratio * 100.0

        # Deductions for text noise/warnings
        if len(warnings) > 1:
            parser_confidence = max(0.0, parser_confidence - 5.0)

        parser_confidence = round(parser_confidence, 1)

        # Flag review_required if parser confidence is under 75.0% or unknown ratio > 40%
        unknown_ratio = unknown_count / candidate_count if candidate_count > 0 else 1.0
        review_required = parser_confidence < 75.0 or unknown_ratio > 0.40

        if review_required:
            if parser_confidence < 75.0:
                warnings.append(
                    f"Low parser confidence ({parser_confidence}%). Manual review of OCR text is recommended."
                )
            if unknown_ratio > 0.40:
                warnings.append(
                    f"High proportion of unrecognized terms ({unknown_count}/{candidate_count}). Manual verification required."
                )

        return {
            "raw_text": raw_text,
            "cleaned_text": cleaned_text,
            "candidate_terms": candidate_terms,
            "match_details": match_details,
            "parser_confidence": parser_confidence,
            "review_required": review_required,
            "warnings": warnings,
            "candidate_count": candidate_count,
            "recognized_count": recognized_count,
            "unknown_count": unknown_count,
        }
