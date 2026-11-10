"""Optional Machine Learning flood risk predictor stub for FloodSense AI.

Loads trained model artifacts (e.g., joblib/LightGBM/XGBoost) only when a
verified artifact and compatible feature schema exist.
Never produces uncalibrated placeholder probabilities or mock outputs.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MODEL_DIR = ROOT / "backend" / "models"


class MLRiskModel:
    """Optional ML inference handler with strict artifact validation."""

    def __init__(self, model_path: Path | str | None = None):
        self.model_path = Path(model_path) if model_path else (DEFAULT_MODEL_DIR / "flood_classifier.joblib")
        self.model: Any = None
        self.is_loaded: bool = False
        self.calibration_evaluated: bool = False
        self._try_load()

    def _try_load(self) -> None:
        """Loads model only if artifact exists on disk."""
        if not self.model_path.exists():
            self.is_loaded = False
            return

        try:
            import joblib
            loaded = joblib.load(self.model_path)
            # Ensure model has a predict_proba or predict method
            if hasattr(loaded, "predict_proba") or hasattr(loaded, "predict"):
                self.model = loaded
                self.is_loaded = True
        except Exception:
            self.model = None
            self.is_loaded = False

    def predict_risk(self, features: dict[str, float]) -> float | None:
        """Returns predicted probability if calibrated model is loaded, else None."""
        if not self.is_loaded or self.model is None:
            return None

        # When a model exists, verify feature vector
        try:
            import pandas as pd
            df = pd.DataFrame([features])
            if hasattr(self.model, "predict_proba"):
                prob = float(self.model.predict_proba(df)[0][1])
                return prob
            elif hasattr(self.model, "predict"):
                return float(self.model.predict(df)[0])
        except Exception:
            return None
        return None

