"""Silent-Face-Anti-Spoofing integration using ONNX Runtime.

Uses an ensemble of two lightweight models (~1.7MB each):
  - MiniFASNetV2 (scale=2.7) — wider crop, captures context
  - MiniFASNetV1SE (scale=4.0) — tighter crop, focuses on face detail

Both models classify faces as Real (index 1) or Fake (index 0/2).
Ensemble prediction averages their softmax outputs for robustness.

No PyTorch dependency — runs on onnxruntime (already in project).
"""

import logging
import os
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

logger = logging.getLogger(__name__)

# Default model directory (alongside this file's parent models dir)
_DEFAULT_MODEL_DIR = os.path.join(
    os.path.dirname(__file__), "..", "models", "anti_spoof"
)


class AntiSpoofModel:
    """Single ONNX anti-spoofing model wrapper."""

    def __init__(self, model_path: str, scale: float, providers: list[str] | None = None):
        if providers is None:
            providers = ["CPUExecutionProvider"]

        self.session = ort.InferenceSession(model_path, providers=providers)
        self.scale = scale

        input_cfg = self.session.get_inputs()[0]
        self.input_name = input_cfg.name
        self.input_size = tuple(input_cfg.shape[2:])  # (80, 80)

        output_cfg = self.session.get_outputs()[0]
        self.output_name = output_cfg.name

        logger.info(
            "Anti-spoof model loaded: %s (scale=%.1f, input=%s)",
            os.path.basename(model_path), scale, self.input_size,
        )

    def _crop_face(self, image: np.ndarray, bbox_xywh: list[int]) -> np.ndarray:
        """Crop face region with scale expansion around center."""
        src_h, src_w = image.shape[:2]
        x, y, box_w, box_h = bbox_xywh

        # Scale factor: expand crop around face, clamped to image bounds
        scale = min(
            (src_h - 1) / max(box_h, 1),
            (src_w - 1) / max(box_w, 1),
            self.scale,
        )
        new_w = box_w * scale
        new_h = box_h * scale

        center_x = x + box_w / 2.0
        center_y = y + box_h / 2.0

        x1 = max(0, int(center_x - new_w / 2))
        y1 = max(0, int(center_y - new_h / 2))
        x2 = min(src_w - 1, int(center_x + new_w / 2))
        y2 = min(src_h - 1, int(center_y + new_h / 2))

        cropped = image[y1: y2 + 1, x1: x2 + 1]
        if cropped.size == 0:
            return np.zeros((*self.input_size, 3), dtype=np.uint8)

        return cv2.resize(cropped, self.input_size[::-1])

    def predict_raw(self, image: np.ndarray, bbox_xyxy: list[float]) -> np.ndarray:
        """Run inference and return raw logits (for ensemble summing).

        Args:
            image: BGR numpy array (full image, not cropped).
            bbox_xyxy: Face bounding box [x1, y1, x2, y2].

        Returns:
            Raw logits array of shape (1, 3).
        """
        x1, y1, x2, y2 = [int(v) for v in bbox_xyxy]
        bbox_xywh = [x1, y1, x2 - x1, y2 - y1]

        face = self._crop_face(image, bbox_xywh)
        tensor = face.astype(np.float32)
        tensor = np.transpose(tensor, (2, 0, 1))  # HWC → CHW
        tensor = np.expand_dims(tensor, axis=0)    # (1, 3, 80, 80)

        outputs = self.session.run([self.output_name], {self.input_name: tensor})
        return outputs[0]  # shape (1, 3)


class AntiSpoofService:
    """Ensemble anti-spoofing using two Silent-Face models.

    Combines MiniFASNetV2 (scale=2.7) and MiniFASNetV1SE (scale=4.0)
    for robust real/fake classification.
    """

    def __init__(
        self,
        model_dir: str | None = None,
        providers: list[str] | None = None,
    ):
        if model_dir is None:
            model_dir = _DEFAULT_MODEL_DIR

        model_dir = str(Path(model_dir).resolve())

        v2_path = os.path.join(model_dir, "MiniFASNetV2.onnx")
        v1se_path = os.path.join(model_dir, "MiniFASNetV1SE.onnx")

        if not os.path.exists(v2_path) or not os.path.exists(v1se_path):
            raise FileNotFoundError(
                f"Anti-spoof models not found in {model_dir}. "
                f"Expected MiniFASNetV2.onnx and MiniFASNetV1SE.onnx"
            )

        self.models = [
            AntiSpoofModel(v2_path, scale=2.7, providers=providers),
            AntiSpoofModel(v1se_path, scale=4.0, providers=providers),
        ]

    @staticmethod
    def _softmax(x: np.ndarray) -> np.ndarray:
        e_x = np.exp(x - np.max(x, axis=1, keepdims=True))
        return e_x / e_x.sum(axis=1, keepdims=True)

    def predict(self, image: np.ndarray, bbox_xyxy: list[float]) -> dict:
        """Run ensemble anti-spoofing prediction.

        Args:
            image: BGR numpy array (full image).
            bbox_xyxy: Face bounding box [x1, y1, x2, y2].

        Returns:
            dict with keys:
                - is_real: bool
                - real_score: float (0-1, probability of being real)
                - fake_score: float (0-1, probability of being fake)
                - label: "Real" or "Fake"
                - raw_label_idx: int (1=Real, 0 or 2=Fake)
        """
        # Ensemble: sum raw logits from both models
        prediction = np.zeros((1, 3), dtype=np.float64)
        for model in self.models:
            raw = model.predict_raw(image, bbox_xyxy)
            prediction += raw.astype(np.float64)

        # Average and softmax
        prediction /= len(self.models)
        probs = self._softmax(prediction)

        label_idx = int(np.argmax(probs[0]))
        # Index 1 = Real, Index 0 or 2 = Fake
        is_real = label_idx == 1
        real_score = float(probs[0, 1])
        fake_score = 1.0 - real_score

        return {
            "is_real": is_real,
            "real_score": round(real_score, 6),
            "fake_score": round(fake_score, 6),
            "label": "Real" if is_real else "Fake",
            "raw_label_idx": label_idx,
        }
