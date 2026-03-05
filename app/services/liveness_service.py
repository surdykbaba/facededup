import logging
from typing import NamedTuple

import cv2
import numpy as np
from insightface.app import FaceAnalysis

from app.config import get_settings
from app.core.exceptions import InvalidImageError, NoFaceDetectedError
from app.services.face_service import FaceService

logger = logging.getLogger(__name__)


class CheckResult(NamedTuple):
    name: str
    passed: bool
    score: float
    detail: str
    mandatory: bool


class LivenessService:
    """Passive liveness detection with anti-spoof checks.

    Checks performed (11 total):
    MANDATORY (all must pass):
      1. Detection confidence (min 0.85)
      2. Landmark geometric quality
      3. HSV skin tone validation
      4. DCT frequency domain analysis
      5. Glare/reflection detection

    OPTIONAL (allow 1 failure):
      6. Sharpness (Laplacian variance)
      7. Texture (LBP variance)
      8. Color distribution
      9. Face size ratio
     10. Embedding norm / quality
     11. Edge density
    """

    def __init__(self, analyzer: FaceAnalysis):
        self.analyzer = analyzer
        self._settings = get_settings()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_liveness(self, image_bytes: bytes) -> dict:
        """Run all liveness checks on raw image bytes.

        Performs face detection internally.
        """
        face_svc = FaceService(self.analyzer)
        img, face, face_crop = face_svc.detect_face(image_bytes)
        return self.check_liveness_from_face(img, face, face_crop)

    def check_liveness_from_face(
        self, img: np.ndarray, face, face_crop: np.ndarray
    ) -> dict:
        """Run all liveness checks on a pre-detected face.

        Use this when the caller already ran face detection (e.g. enrollment)
        to avoid a redundant InsightFace inference pass.
        """
        h, w = img.shape[:2]
        gray_face = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
        bbox = face.bbox.astype(int)

        s = self._settings

        all_checks = [
            # Mandatory
            self._check_detection_confidence(face, s.LIVENESS_DET_SCORE_MIN),
            self._check_landmark_quality(face),
            self._check_skin_tone(face_crop, s),
            self._check_frequency_domain(face_crop, s.LIVENESS_DCT_HIGH_FREQ_MIN),
            self._check_glare(gray_face, s.LIVENESS_GLARE_RATIO_MAX),
            # Optional
            self._check_sharpness(gray_face, s.LIVENESS_SHARPNESS_MIN, s.LIVENESS_SHARPNESS_MAX),
            self._check_texture(gray_face, s.LIVENESS_LBP_VARIANCE_MIN),
            self._check_color_distribution(face_crop, s.LIVENESS_COLOR_STD_MIN),
            self._check_face_size_ratio(bbox, w, h, s.LIVENESS_FACE_SIZE_RATIO_MIN, s.LIVENESS_FACE_SIZE_RATIO_MAX),
            self._check_embedding_quality(face, s.LIVENESS_EMBEDDING_NORM_MIN, s.LIVENESS_EMBEDDING_NORM_MAX),
            self._check_edge_density(face_crop, s.LIVENESS_EDGE_DENSITY_MIN, s.LIVENESS_EDGE_DENSITY_MAX),
        ]

        # Two-tier verdict
        mandatory = [c for c in all_checks if c.mandatory]
        optional = [c for c in all_checks if not c.mandatory]

        mandatory_passed = sum(1 for c in mandatory if c.passed)
        optional_passed = sum(1 for c in optional if c.passed)

        all_mandatory_ok = mandatory_passed == len(mandatory)
        optional_ok = optional_passed >= len(optional) - 1  # allow 1 failure

        is_live = all_mandatory_ok and optional_ok

        total = len(all_checks)
        total_passed = mandatory_passed + optional_passed
        liveness_score = total_passed / total if total > 0 else 0.0

        # Build checks dict for response
        checks = {}
        for c in all_checks:
            checks[c.name] = {
                "score": c.score,
                "passed": c.passed,
                "detail": c.detail,
                "mandatory": c.mandatory,
            }

        face_info = FaceService.extract_face_info(face)

        logger.info(
            "Liveness check: score=%.2f passed=%d/%d mandatory=%d/%d live=%s",
            liveness_score, total_passed, total,
            mandatory_passed, len(mandatory), is_live,
        )

        return {
            "is_live": is_live,
            "liveness_score": round(liveness_score, 4),
            "checks_passed": total_passed,
            "checks_total": total,
            "mandatory_checks_passed": mandatory_passed,
            "mandatory_checks_total": len(mandatory),
            "checks": checks,
            "face_info": face_info,
        }

    # ------------------------------------------------------------------
    # Mandatory checks
    # ------------------------------------------------------------------

    @staticmethod
    def _check_detection_confidence(face, min_score: float) -> CheckResult:
        det_score = float(face.det_score)
        passed = det_score >= min_score
        return CheckResult(
            name="detection_confidence",
            passed=passed,
            score=round(det_score, 4),
            detail=f"Detection score: {det_score:.4f} (min: {min_score})",
            mandatory=True,
        )

    @staticmethod
    def _check_landmark_quality(face) -> CheckResult:
        """Evaluate facial landmark geometric consistency.

        InsightFace kps: 5 points (left_eye, right_eye, nose, left_mouth, right_mouth).
        Cartoons have distorted landmark geometry.
        """
        if not hasattr(face, "kps") or face.kps is None:
            return CheckResult(
                name="landmark_quality", passed=False, score=0.0,
                detail="No landmarks available", mandatory=True,
            )

        kps = face.kps
        left_eye, right_eye, nose, left_mouth, right_mouth = kps

        bbox = face.bbox
        face_width = float(bbox[2] - bbox[0])
        face_height = float(bbox[3] - bbox[1])

        if face_width < 10 or face_height < 10:
            return CheckResult(
                name="landmark_quality", passed=False, score=0.0,
                detail="Face too small for landmark analysis", mandatory=True,
            )

        sub_scores = 0.0
        sub_total = 4

        # 1. Inter-eye distance ratio (typically 0.25-0.55 of face width)
        eye_dist = float(np.linalg.norm(left_eye - right_eye))
        eye_ratio = eye_dist / face_width
        if 0.25 <= eye_ratio <= 0.55:
            sub_scores += 1.0

        # 2. Nose position: centered between eyes, below eye midpoint
        eye_mid = (left_eye + right_eye) / 2
        nose_x_offset = abs(nose[0] - eye_mid[0]) / face_width
        nose_below = (nose[1] - eye_mid[1]) / face_height
        if nose_x_offset < 0.15 and 0.05 < nose_below < 0.40:
            sub_scores += 1.0

        # 3. Mouth position: below nose, roughly centered
        mouth_mid = (left_mouth + right_mouth) / 2
        mouth_below_nose = (mouth_mid[1] - nose[1]) / face_height
        mouth_centered = abs(mouth_mid[0] - nose[0]) / face_width
        if 0.03 < mouth_below_nose < 0.35 and mouth_centered < 0.12:
            sub_scores += 1.0

        # 4. Face symmetry: nose-to-eye distances should be similar
        dist_nose_left = float(np.linalg.norm(nose - left_eye))
        dist_nose_right = float(np.linalg.norm(nose - right_eye))
        symmetry = min(dist_nose_left, dist_nose_right) / max(dist_nose_left, dist_nose_right) if max(dist_nose_left, dist_nose_right) > 0 else 0
        if symmetry > 0.65:
            sub_scores += 1.0

        score = sub_scores / sub_total
        passed = score >= 0.65

        return CheckResult(
            name="landmark_quality",
            passed=passed,
            score=round(score, 4),
            detail=f"Landmark quality: {score:.4f} (eye_ratio={eye_ratio:.3f}, symmetry={symmetry:.3f})",
            mandatory=True,
        )

    @staticmethod
    def _check_skin_tone(face_crop: np.ndarray, settings) -> CheckResult:
        """Validate that face contains realistic skin-toned pixels in HSV space.

        Human skin: H ~0-50 (and 160-180 for red wrap), S 15-200, V 50-255.
        Cartoons often have flat fills or non-skin colors.
        """
        hsv = cv2.cvtColor(face_crop, cv2.COLOR_BGR2HSV)
        h_ch, s_ch, _ = cv2.split(hsv)

        lower1 = np.array([0, settings.LIVENESS_SKIN_SAT_MIN, 50], dtype=np.uint8)
        upper1 = np.array([50, settings.LIVENESS_SKIN_SAT_MAX, 255], dtype=np.uint8)
        mask1 = cv2.inRange(hsv, lower1, upper1)

        # Red wrap-around
        lower2 = np.array([160, settings.LIVENESS_SKIN_SAT_MIN, 50], dtype=np.uint8)
        upper2 = np.array([180, settings.LIVENESS_SKIN_SAT_MAX, 255], dtype=np.uint8)
        mask2 = cv2.inRange(hsv, lower2, upper2)

        skin_mask = cv2.bitwise_or(mask1, mask2)
        total_pixels = skin_mask.size
        skin_ratio = float(np.count_nonzero(skin_mask)) / total_pixels if total_pixels > 0 else 0

        # Check saturation variance of skin pixels (flat cartoon fills have low std)
        flat_fill = False
        if skin_ratio > 0.10:
            skin_s = s_ch[skin_mask > 0]
            if len(skin_s) > 10:
                skin_s_std = float(np.std(skin_s))
                flat_fill = skin_s_std < 8.0
            else:
                flat_fill = True

        passed = skin_ratio >= settings.LIVENESS_SKIN_PIXEL_RATIO_MIN and not flat_fill

        return CheckResult(
            name="skin_tone",
            passed=passed,
            score=round(skin_ratio, 4),
            detail=f"Skin pixel ratio: {skin_ratio:.4f} (min: {settings.LIVENESS_SKIN_PIXEL_RATIO_MIN}), flat_fill={flat_fill}",
            mandatory=True,
        )

    @staticmethod
    def _check_frequency_domain(face_crop: np.ndarray, min_ratio: float) -> CheckResult:
        """DCT frequency analysis to detect print/screen recapture attacks.

        Real camera captures have natural high-frequency sensor noise.
        Print/screen recaptures lose high-frequency content.
        """
        gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
        gray_resized = cv2.resize(gray, (128, 128))

        float_img = np.float32(gray_resized)
        dct = cv2.dct(float_img)

        total_energy = float(np.sum(np.abs(dct)))
        if total_energy == 0:
            return CheckResult(
                name="frequency_analysis", passed=False, score=0.0,
                detail="Zero energy in DCT", mandatory=True,
            )

        h, w = dct.shape
        high_freq = dct[h // 2:, w // 2:]
        high_freq_energy = float(np.sum(np.abs(high_freq)))
        high_freq_ratio = high_freq_energy / total_energy

        passed = high_freq_ratio >= min_ratio

        return CheckResult(
            name="frequency_analysis",
            passed=passed,
            score=round(high_freq_ratio, 6),
            detail=f"DCT high-freq ratio: {high_freq_ratio:.6f} (min: {min_ratio})",
            mandatory=True,
        )

    @staticmethod
    def _check_glare(gray_face: np.ndarray, max_ratio: float) -> CheckResult:
        glare_pixels = int(np.sum(gray_face > 240))
        total = gray_face.size
        glare_ratio = glare_pixels / total if total > 0 else 0.0
        passed = glare_ratio < max_ratio
        return CheckResult(
            name="glare_detection",
            passed=passed,
            score=round(glare_ratio, 4),
            detail=f"Glare pixel ratio: {glare_ratio:.4f} (max: {max_ratio})",
            mandatory=True,
        )

    # ------------------------------------------------------------------
    # Optional checks
    # ------------------------------------------------------------------

    @staticmethod
    def _check_sharpness(gray_face: np.ndarray, min_val: float, max_val: float) -> CheckResult:
        laplacian = cv2.Laplacian(gray_face, cv2.CV_64F)
        sharpness = float(laplacian.var())
        passed = min_val <= sharpness <= max_val
        return CheckResult(
            name="sharpness",
            passed=passed,
            score=round(sharpness, 2),
            detail=f"Laplacian variance: {sharpness:.2f} (range: {min_val}-{max_val})",
            mandatory=False,
        )

    @staticmethod
    def _check_texture(gray_face: np.ndarray, min_variance: float) -> CheckResult:
        """LBP variance — real faces have rich micro-texture."""
        padded = cv2.copyMakeBorder(gray_face, 1, 1, 1, 1, cv2.BORDER_REFLECT)
        h, w = gray_face.shape
        lbp = np.zeros_like(gray_face, dtype=np.uint8)

        offsets = [(-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1)]
        for i, (dy, dx) in enumerate(offsets):
            neighbor = padded[1 + dy: 1 + dy + h, 1 + dx: 1 + dx + w]
            lbp |= ((neighbor >= gray_face).astype(np.uint8) << i)

        lbp_var = float(np.var(lbp.astype(np.float64)))
        passed = lbp_var >= min_variance
        return CheckResult(
            name="texture",
            passed=passed,
            score=round(lbp_var, 2),
            detail=f"LBP variance: {lbp_var:.2f} (min: {min_variance})",
            mandatory=False,
        )

    @staticmethod
    def _check_color_distribution(face_crop: np.ndarray, min_std: float) -> CheckResult:
        color_stds = [float(np.std(ch)) for ch in cv2.split(face_crop)]
        avg_std = float(np.mean(color_stds))
        passed = avg_std >= min_std
        return CheckResult(
            name="color_distribution",
            passed=passed,
            score=round(avg_std, 2),
            detail=f"Avg channel std: {avg_std:.2f} (min: {min_std})",
            mandatory=False,
        )

    @staticmethod
    def _check_face_size_ratio(
        bbox: np.ndarray, img_w: int, img_h: int,
        min_ratio: float, max_ratio: float,
    ) -> CheckResult:
        x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
        face_area = max(0, x2 - x1) * max(0, y2 - y1)
        image_area = img_w * img_h
        ratio = face_area / image_area if image_area > 0 else 0.0
        passed = min_ratio <= ratio <= max_ratio
        return CheckResult(
            name="face_size_ratio",
            passed=passed,
            score=round(ratio, 4),
            detail=f"Face/image ratio: {ratio:.4f} (range: {min_ratio}-{max_ratio})",
            mandatory=False,
        )

    @staticmethod
    def _check_embedding_quality(face, min_norm: float, max_norm: float) -> CheckResult:
        """Raw embedding L2 norm indicates face quality.

        Real faces typically produce norms of 20-28.
        Cartoons/degraded images produce lower or extreme norms.
        """
        if not hasattr(face, "embedding") or face.embedding is None:
            return CheckResult(
                name="embedding_quality", passed=False, score=0.0,
                detail="No raw embedding available", mandatory=False,
            )

        norm = float(np.linalg.norm(face.embedding))
        passed = min_norm <= norm <= max_norm
        return CheckResult(
            name="embedding_quality",
            passed=passed,
            score=round(norm, 2),
            detail=f"Embedding L2 norm: {norm:.2f} (range: {min_norm}-{max_norm})",
            mandatory=False,
        )

    @staticmethod
    def _check_edge_density(
        face_crop: np.ndarray, min_density: float, max_density: float,
    ) -> CheckResult:
        """Edge density and distribution analysis.

        Real faces: moderate, evenly distributed edges.
        Cartoons: strong outlines with flat interiors (uneven distribution).
        """
        gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)

        median_val = float(np.median(gray))
        lower = int(max(0, 0.67 * median_val))
        upper = int(min(255, 1.33 * median_val))
        edges = cv2.Canny(gray, lower, upper)

        edge_density = float(np.count_nonzero(edges)) / edges.size if edges.size > 0 else 0.0

        # Check edge distribution uniformity via 4x4 grid
        gh, gw = edges.shape[0] // 4, edges.shape[1] // 4
        edge_uniformity_std = 0.0
        if gh > 0 and gw > 0:
            grid_densities = []
            for i in range(4):
                for j in range(4):
                    cell = edges[i * gh:(i + 1) * gh, j * gw:(j + 1) * gw]
                    grid_densities.append(
                        float(np.count_nonzero(cell)) / cell.size if cell.size > 0 else 0.0
                    )
            edge_uniformity_std = float(np.std(grid_densities))

        density_ok = min_density <= edge_density <= max_density
        not_cartoon_edges = edge_uniformity_std < 0.15
        passed = density_ok and not_cartoon_edges

        return CheckResult(
            name="edge_density",
            passed=passed,
            score=round(edge_density, 4),
            detail=f"Edge density: {edge_density:.4f} (range: {min_density}-{max_density}), uniformity_std: {edge_uniformity_std:.4f}",
            mandatory=False,
        )
