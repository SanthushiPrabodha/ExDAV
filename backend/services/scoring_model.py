"""
scoring_model.py — Learned Scoring Layer for Ex-DAV
=====================================================
Extracts a structured feature vector from pipeline outputs and passes it
through a weighted scoring model to produce a calibrated verdict and
confidence score.

This module replaces the ad-hoc weighted-sum in pipeline_service.py with
an explicit, trainable scoring model.  In the current version the weights
are set by domain knowledge (interpretable baseline).  They can be updated
with learned weights from sklearn LogisticRegression or a decision tree
once a labelled dataset is available — making the "AI" reasoning component
genuine rather than purely rule-based.

Architecture
------------
1. Feature extraction   → FeatureVector  (7 normalised float features)
2. Linear scoring       → raw_score ∈ [0, 1]
3. Calibration          → calibrated_confidence with Platt-style sigmoid
4. Verdict mapping      → Authentic / Suspicious / Inconclusive / Counterfeit
5. Feature importance   → which features most influenced this decision

References
----------
• Platt, J. (1999). Probabilistic outputs for support vector machines.
• Zadrozny & Elkan (2002). Transforming classifier scores into probabilities.
• ICH Q10 Pharmaceutical Quality System — risk-based scoring rationale.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# FEATURE VECTOR
# ---------------------------------------------------------------------------

@dataclass
class FeatureVector:
    """
    Seven binary/continuous features extracted from pipeline outputs.
    All values are normalised to [0, 1].

    Feature descriptions with regulatory justification:
    ---------------------------------------------------
    F1  drug_name_present     Binary — product name identified.
                              (NMRA / SPC §1 mandatory)
    F2  batch_present         Binary — batch/lot number found.
                              (GMP traceability requirement)
    F3  expiry_present        Binary — expiry date found.
                              (NMRA / BNF mandatory)
    F4  manufacturer_present  Binary — manufacturer identity found.
                              (NMRA / WHO mandatory)
    F5  expiry_valid          Binary — expiry date is in the future.
                              (patient safety)
    F6  logo_present          Binary — ≥1 known brand/logo detected.
                              (brand authenticity indicator)
    F7  completeness_score    Continuous [0,1] — fraction of mandatory
                              fields populated (from run_pipeline).
    """
    drug_name_present: float = 0.0
    batch_present: float = 0.0
    expiry_present: float = 0.0
    manufacturer_present: float = 0.0
    expiry_valid: float = 0.0
    logo_present: float = 0.0
    completeness_score: float = 0.0

    def as_list(self) -> List[float]:
        return [
            self.drug_name_present,
            self.batch_present,
            self.expiry_present,
            self.manufacturer_present,
            self.expiry_valid,
            self.logo_present,
            self.completeness_score,
        ]

    @staticmethod
    def names() -> List[str]:
        return [
            "drug_name_present",
            "batch_present",
            "expiry_present",
            "manufacturer_present",
            "expiry_valid",
            "logo_present",
            "completeness_score",
        ]


# ---------------------------------------------------------------------------
# MODEL WEIGHTS
# ---------------------------------------------------------------------------

# Domain-knowledge baseline weights (sum ≈ 1.0).
# Interpretation: how much each feature contributes to the authenticity
# score.  Weights were derived from NMRA/GMP/BNF severity rankings:
#   - Expiry validity is the strongest safety signal.
#   - Drug name + manufacturer are the primary identity signals.
#   - Batch number enables traceability but does not alone determine
#     authenticity.
#   - Logo presence is a secondary corroborating signal.
#   - Completeness score aggregates all fields holistically.
#
# To update with learned weights:
#   from sklearn.linear_model import LogisticRegression
#   model = LogisticRegression()
#   model.fit(X_train, y_train)
#   LEARNED_WEIGHTS = dict(zip(FeatureVector.names(), model.coef_[0]))
DEFAULT_WEIGHTS: Dict[str, float] = {
    "drug_name_present":    0.20,
    "batch_present":        0.10,
    "expiry_present":       0.15,
    "manufacturer_present": 0.18,
    "expiry_valid":         0.22,
    "logo_present":         0.07,
    "completeness_score":   0.08,
}

# Verdict thresholds on the raw authenticity score
_THRESHOLD_AUTHENTIC:   float = 0.72   # score ≥ this → Authentic
_THRESHOLD_SUSPICIOUS:  float = 0.45   # score ≥ this → Suspicious
_THRESHOLD_COUNTERFEIT: float = 0.20   # score < this → Counterfeit
                                        # between 0.20–0.44 → Inconclusive


# ---------------------------------------------------------------------------
# SCORING MODEL
# ---------------------------------------------------------------------------

@dataclass
class ScoringResult:
    verdict: str
    confidence: float          # calibrated probability [0, 1]
    raw_score: float           # weighted sum before calibration
    feature_vector: FeatureVector
    feature_importances: Dict[str, float] = field(default_factory=dict)
    explanation_snippet: str = ""


class ExDAVScoringModel:
    """
    Interpretable weighted scoring model for Ex-DAV.

    In research mode (weights=DEFAULT_WEIGHTS) this is a transparent
    linear classifier with Platt sigmoid calibration — fully interpretable
    and auditable, satisfying XAI requirements.

    Once a labelled dataset is available, replace DEFAULT_WEIGHTS with
    weights learned from LogisticRegression.fit(X, y) and the model
    upgrades to a data-driven classifier with no architectural change.
    """

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.weights = weights or DEFAULT_WEIGHTS.copy()
        # Platt calibration parameters (A, B) — defaults tuned empirically.
        # Retrain with: sklearn.calibration.CalibratedClassifierCV
        self._platt_a: float = -4.0
        self._platt_b: float = 2.0

    # ── Feature extraction ───────────────────────────────────────────────

    @staticmethod
    def extract_features(
        metadata: Dict[str, Any],
        validation_results: List[Dict[str, Any]],
        completeness_score: float,
    ) -> FeatureVector:
        """
        Extract a normalised FeatureVector from pipeline outputs.

        Parameters
        ----------
        metadata           : dict from pipeline_service (drug_name, batch, …)
        validation_results : list of validation dicts (guideline, status, …)
        completeness_score : float from run_pipeline (0–1)
        """
        # F1–F4: mandatory field presence
        drug_name_present    = 1.0 if metadata.get("drug_name")    else 0.0
        batch_present        = 1.0 if metadata.get("batch_number") else 0.0
        expiry_present       = 1.0 if metadata.get("expiry_date")  else 0.0
        manufacturer_present = 1.0 if metadata.get("manufacturer") else 0.0

        # F5: expiry validity
        expiry_valid = 0.0
        expiry_str = metadata.get("expiry_date", "")
        if expiry_str:
            expiry_valid = _check_expiry_valid(expiry_str)

        # F6: logo presence
        logo_present = 1.0 if metadata.get("detected_logos") else 0.0

        # F7: overall completeness
        completeness = max(0.0, min(1.0, completeness_score or 0.0))

        return FeatureVector(
            drug_name_present=drug_name_present,
            batch_present=batch_present,
            expiry_present=expiry_present,
            manufacturer_present=manufacturer_present,
            expiry_valid=expiry_valid,
            logo_present=logo_present,
            completeness_score=completeness,
        )

    # ── Scoring ──────────────────────────────────────────────────────────

    def score(
        self,
        metadata: Dict[str, Any],
        validation_results: List[Dict[str, Any]],
        completeness_score: float,
        has_critical_failure: bool = False,
    ) -> ScoringResult:
        """
        Compute verdict + calibrated confidence from pipeline outputs.

        Parameters
        ----------
        metadata             : metadata dict from pipeline
        validation_results   : validation result list from pipeline
        completeness_score   : fraction of mandatory fields populated
        has_critical_failure : True when a hard rule failure occurred
                               (e.g. expired product, batch format invalid)
        """
        fv = self.extract_features(metadata, validation_results, completeness_score)
        features = fv.as_list()
        names = FeatureVector.names()

        # Weighted sum
        raw = sum(self.weights.get(n, 0.0) * v for n, v in zip(names, features))

        # Hard cap for critical failures (expired product, etc.)
        if has_critical_failure:
            raw = min(raw, _THRESHOLD_SUSPICIOUS - 0.01)

        # Platt sigmoid calibration:  p = 1 / (1 + exp(A * raw + B))
        calibrated = 1.0 / (1.0 + math.exp(self._platt_a * raw + self._platt_b))
        calibrated = round(max(0.0, min(1.0, calibrated)), 3)

        # Verdict mapping
        verdict = _score_to_verdict(raw, has_critical_failure)

        # Feature importances (contribution of each feature to raw score)
        importances = {
            n: round(self.weights.get(n, 0.0) * v, 4)
            for n, v in zip(names, features)
        }
        top_features = sorted(importances.items(), key=lambda x: -x[1])[:3]
        top_str = ", ".join(
            f"{n.replace('_', ' ')} ({v:.2f})" for n, v in top_features
        )
        snippet = (
            f"Scoring model: raw={raw:.3f}, calibrated_confidence={calibrated:.3f}. "
            f"Top contributing features: {top_str}."
        )

        return ScoringResult(
            verdict=verdict,
            confidence=calibrated,
            raw_score=round(raw, 4),
            feature_vector=fv,
            feature_importances=importances,
            explanation_snippet=snippet,
        )

    # ── Serialisation ────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {"weights": self.weights, "platt_a": self._platt_a,
                "platt_b": self._platt_b}


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _check_expiry_valid(expiry_str: str) -> float:
    """Return 1.0 if the expiry date is in the future, else 0.0."""
    import re
    now = datetime.now()
    for pattern in [
        r"(\d{1,2})[\/\-](\d{4})",   # MM/YYYY or MM-YYYY
        r"(\d{4})[\/\-](\d{1,2})",   # YYYY/MM
        r"(\d{1,2})[\/\-](\d{2})$",  # MM/YY
    ]:
        m = re.search(pattern, expiry_str)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if b < 100:               # two-digit year
                b += 2000
            if a > 12:                # YYYY/MM format
                a, b = b, a
            try:
                if b > now.year or (b == now.year and a >= now.month):
                    return 1.0
                return 0.0
            except Exception:
                pass
    return 0.5  # format not parseable — neither valid nor invalid


def _score_to_verdict(raw: float, has_critical_failure: bool) -> str:
    if has_critical_failure and raw < _THRESHOLD_AUTHENTIC:
        return "Suspicious"
    if raw >= _THRESHOLD_AUTHENTIC:
        return "Authentic"
    if raw >= _THRESHOLD_SUSPICIOUS:
        return "Suspicious"
    if raw < _THRESHOLD_COUNTERFEIT:
        return "Counterfeit"
    return "Inconclusive"


# ---------------------------------------------------------------------------
# MODULE-LEVEL SINGLETON
# ---------------------------------------------------------------------------

_model: Optional[ExDAVScoringModel] = None


def get_model() -> ExDAVScoringModel:
    """Return the shared scoring model instance (created on first call)."""
    global _model
    if _model is None:
        _model = ExDAVScoringModel()
    return _model
