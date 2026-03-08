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

    def _decode_and_resize(self, image_bytes: bytes) -> np.ndarray:
        """Decode image bytes and resize if too large."""
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise InvalidImageError("Could not decode image data")

        h, w = img.shape[:2]
        max_dim = 640  # Keep close to det_size to avoid wasted resize
        if max(h, w) > max_dim:
            scale = max_dim / max(h, w)
            img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        return img

    def _get_single_face(self, img: np.ndarray):
        """Run InsightFace detection and return exactly one face object."""
        faces = self.analyzer.get(img)
        if len(faces) == 0:
            raise NoFaceDetectedError()
        if len(faces) > 1:
            raise MultipleFacesError(f"Expected 1 face, found {len(faces)}")
        return faces[0]

    @staticmethod
    def extract_face_info(face) -> dict:
        """Extract metadata dict from an InsightFace face object."""
        face_info = {
            "bbox": face.bbox.tolist(),
            "det_score": round(float(face.det_score), 4),
        }
        if hasattr(face, "age"):
            face_info["age"] = int(face.age)
        if hasattr(face, "gender"):
            face_info["gender"] = "M" if int(face.gender) == 1 else "F"
        return face_info

    @staticmethod
    def crop_face(img: np.ndarray, face) -> np.ndarray:
        """Crop face region from image using bbox, clamped to bounds."""
        h, w = img.shape[:2]
        bbox = face.bbox.astype(int)
        x1 = max(0, bbox[0])
        y1 = max(0, bbox[1])
        x2 = min(w, bbox[2])
        y2 = min(h, bbox[3])
        return img[y1:y2, x1:x2]

    def detect_face(self, image_bytes: bytes) -> tuple[np.ndarray, object, np.ndarray]:
        """Detect a single face and return image, face object, and face crop.

        Used when both liveness checks and embedding extraction are needed
        on the same image (avoids running InsightFace inference twice).

        Returns:
            Tuple of (img_array, face_object, face_crop).
        """
        img = self._decode_and_resize(image_bytes)
        face = self._get_single_face(img)
        face_crop = self.crop_face(img, face)

        if face_crop.size == 0:
            raise NoFaceDetectedError("Face bounding box is invalid")

        logger.info(
            "Face detected: score=%.4f bbox=%s",
            face.det_score,
            face.bbox.tolist(),
        )
        return img, face, face_crop

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
        img, face, _ = self.detect_face(image_bytes)
        embedding = face.normed_embedding
        face_info = self.extract_face_info(face)
        return embedding, face_info
