import logging

import cv2
import numpy as np
from insightface.app import FaceAnalysis

from app.core.exceptions import (
    InvalidImageError,
    MultipleFacesError,
    NoFaceDetectedError,
)

logger = logging.getLogger(__name__)


class FaceService:
    def __init__(self, analyzer: FaceAnalysis):
        self.analyzer = analyzer

    def detect_and_embed(self, image_bytes: bytes) -> tuple[np.ndarray, dict]:
        """Detect a single face and return its normalized 512-dim embedding.

        Args:
            image_bytes: Raw image bytes (JPEG/PNG).

        Returns:
            Tuple of (embedding ndarray, face_info dict).

        Raises:
            InvalidImageError: Cannot decode image.
            NoFaceDetectedError: No face found.
            MultipleFacesError: More than one face found.
        """
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise InvalidImageError("Could not decode image data")

        # Resize large images to speed up inference
        h, w = img.shape[:2]
        max_dim = 1280
        if max(h, w) > max_dim:
            scale = max_dim / max(h, w)
            img = cv2.resize(img, (int(w * scale), int(h * scale)))

        faces = self.analyzer.get(img)

        if len(faces) == 0:
            raise NoFaceDetectedError()
        if len(faces) > 1:
            raise MultipleFacesError(f"Expected 1 face, found {len(faces)}")

        face = faces[0]
        embedding = face.normed_embedding  # L2-normalized by InsightFace

        face_info = {
            "bbox": face.bbox.tolist(),
            "det_score": round(float(face.det_score), 4),
        }
        if hasattr(face, "age"):
            face_info["age"] = int(face.age)
        if hasattr(face, "gender"):
            face_info["gender"] = "M" if int(face.gender) == 1 else "F"

        logger.info(
            "Face detected: score=%.4f bbox=%s",
            face.det_score,
            face.bbox.tolist(),
        )
        return embedding, face_info
