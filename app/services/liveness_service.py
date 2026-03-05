import logging

import cv2
import numpy as np
from insightface.app import FaceAnalysis

from app.core.exceptions import InvalidImageError, NoFaceDetectedError

logger = logging.getLogger(__name__)


class LivenessService:
    """Passive liveness detection using image quality and texture analysis.

    Checks performed:
    1. Face detection confidence score
    2. Image sharpness (Laplacian variance) - blurry = likely screen/printout
    3. Texture analysis (LBP variance) - flat texture = likely printed/screen
    4. Color distribution analysis - unnatural color = likely spoofed
    5. Face size ratio - too small or too large relative to frame = suspicious
    6. Reflection/glare detection - screens often produce specular highlights
    """

    # Thresholds (tuned for common spoof scenarios)
    SHARPNESS_MIN = 50.0  # Laplacian variance below this = too blurry
    SHARPNESS_MAX = 2500.0  # Above this = potentially a high-res printout scan
    LBP_VARIANCE_MIN = 300.0  # Low texture variance = flat/printed surface
    FACE_SIZE_RATIO_MIN = 0.05  # Face too small relative to image
    FACE_SIZE_RATIO_MAX = 0.85  # Face fills nearly entire frame (held-up photo)
    DET_SCORE_MIN = 0.7  # Minimum detection confidence
    COLOR_STD_MIN = 15.0  # Very low color variance = artificial image

    def __init__(self, analyzer: FaceAnalysis):
        self.analyzer = analyzer

    def check_liveness(self, image_bytes: bytes) -> dict:
        """Run passive liveness checks on a face image.

        Returns dict with overall liveness verdict and individual check scores.
        """
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise InvalidImageError("Could not decode image data")

        h, w = img.shape[:2]

        # Resize for consistent analysis
        max_dim = 1280
        if max(h, w) > max_dim:
            scale = max_dim / max(h, w)
            img = cv2.resize(img, (int(w * scale), int(h * scale)))
            h, w = img.shape[:2]

        # Detect face
        faces = self.analyzer.get(img)
        if len(faces) == 0:
            raise NoFaceDetectedError()

        # Use the largest/highest-confidence face
        face = max(faces, key=lambda f: float(f.det_score))
        bbox = face.bbox.astype(int)
        x1, y1, x2, y2 = bbox[0], bbox[1], bbox[2], bbox[3]

        # Clamp to image bounds
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(w, x2)
        y2 = min(h, y2)

        face_crop = img[y1:y2, x1:x2]
        if face_crop.size == 0:
            raise NoFaceDetectedError("Face bounding box is invalid")

        checks = {}
        passed = 0
        total = 6

        # 1. Detection confidence
        det_score = float(face.det_score)
        det_pass = det_score >= self.DET_SCORE_MIN
        checks["detection_confidence"] = {
            "score": round(det_score, 4),
            "passed": det_pass,
            "detail": f"Face detection score: {det_score:.4f} (min: {self.DET_SCORE_MIN})",
        }
        if det_pass:
            passed += 1

        # 2. Sharpness (Laplacian variance on face region)
        gray_face = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
        laplacian = cv2.Laplacian(gray_face, cv2.CV_64F)
        sharpness = float(laplacian.var())
        sharp_pass = self.SHARPNESS_MIN <= sharpness <= self.SHARPNESS_MAX
        checks["sharpness"] = {
            "score": round(sharpness, 2),
            "passed": sharp_pass,
            "detail": f"Laplacian variance: {sharpness:.2f} (range: {self.SHARPNESS_MIN}-{self.SHARPNESS_MAX})",
        }
        if sharp_pass:
            passed += 1

        # 3. Texture analysis (LBP variance)
        lbp_var = self._compute_lbp_variance(gray_face)
        texture_pass = lbp_var >= self.LBP_VARIANCE_MIN
        checks["texture"] = {
            "score": round(lbp_var, 2),
            "passed": texture_pass,
            "detail": f"LBP variance: {lbp_var:.2f} (min: {self.LBP_VARIANCE_MIN})",
        }
        if texture_pass:
            passed += 1

        # 4. Color distribution
        color_stds = []
        for ch in cv2.split(face_crop):
            color_stds.append(float(np.std(ch)))
        avg_color_std = np.mean(color_stds)
        color_pass = avg_color_std >= self.COLOR_STD_MIN
        checks["color_distribution"] = {
            "score": round(avg_color_std, 2),
            "passed": color_pass,
            "detail": f"Avg channel std: {avg_color_std:.2f} (min: {self.COLOR_STD_MIN})",
        }
        if color_pass:
            passed += 1

        # 5. Face size ratio
        face_area = (x2 - x1) * (y2 - y1)
        image_area = w * h
        size_ratio = face_area / image_area if image_area > 0 else 0
        size_pass = self.FACE_SIZE_RATIO_MIN <= size_ratio <= self.FACE_SIZE_RATIO_MAX
        checks["face_size_ratio"] = {
            "score": round(size_ratio, 4),
            "passed": size_pass,
            "detail": f"Face/image ratio: {size_ratio:.4f} (range: {self.FACE_SIZE_RATIO_MIN}-{self.FACE_SIZE_RATIO_MAX})",
        }
        if size_pass:
            passed += 1

        # 6. Reflection/glare detection
        gray_full = cv2.cvtColor(img[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
        glare_pixels = np.sum(gray_full > 240)
        glare_ratio = glare_pixels / gray_full.size if gray_full.size > 0 else 0
        glare_pass = glare_ratio < 0.05  # Less than 5% overexposed pixels
        checks["glare_detection"] = {
            "score": round(glare_ratio, 4),
            "passed": glare_pass,
            "detail": f"Glare pixel ratio: {glare_ratio:.4f} (max: 0.05)",
        }
        if glare_pass:
            passed += 1

        # Overall verdict
        liveness_score = passed / total
        is_live = passed >= 5  # Must pass at least 5 of 6 checks

        logger.info(
            "Liveness check: score=%.2f passed=%d/%d live=%s",
            liveness_score, passed, total, is_live,
        )

        return {
            "is_live": is_live,
            "liveness_score": round(liveness_score, 4),
            "checks_passed": passed,
            "checks_total": total,
            "checks": checks,
            "face_info": {
                "bbox": face.bbox.tolist(),
                "det_score": round(det_score, 4),
            },
        }

    @staticmethod
    def _compute_lbp_variance(gray: np.ndarray) -> float:
        """Compute Local Binary Pattern variance as a texture metric.

        Real faces have rich micro-texture; printed/screen images have
        smoother or patterned texture with lower variance.
        """
        # Simplified LBP: compare each pixel to its 8 neighbors
        padded = cv2.copyMakeBorder(gray, 1, 1, 1, 1, cv2.BORDER_REFLECT)
        h, w = gray.shape
        lbp = np.zeros_like(gray, dtype=np.uint8)

        offsets = [(-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1)]
        for i, (dy, dx) in enumerate(offsets):
            neighbor = padded[1 + dy : 1 + dy + h, 1 + dx : 1 + dx + w]
            lbp |= ((neighbor >= gray).astype(np.uint8) << i)

        return float(np.var(lbp.astype(np.float64)))
