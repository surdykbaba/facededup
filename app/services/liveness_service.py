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
    """Liveness detection combining ML anti-spoof with heuristic checks.

    Checks performed (up to 17 total):
    MANDATORY (all must pass):
      1. Detection confidence
      2. Landmark geometric quality
      3. HSV skin tone validation
      4. DCT frequency domain analysis
      5. Glare/reflection detection
      6. Texture / LBP variance
      7. Edge density + uniformity
      8. Lower face visibility (rejects face masks)
      9. Eye visibility (rejects sunglasses)

    OPTIONAL (configurable tolerance, default allow 3 failures):
      0. ML Anti-Spoof model (Silent-Face ensemble, if loaded)
     10. Camera noise pattern
     11. Color channel correlation
     12. Sharpness (Laplacian variance)
     13. Color distribution
     14. Face size ratio
     15. Embedding norm / quality
     16. Gradient smoothness (AI image detection)
    """

    def __init__(self, analyzer: FaceAnalysis, anti_spoof=None):
        self.analyzer = analyzer
        self.anti_spoof = anti_spoof
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
            # Mandatory (9 heuristic checks — ALL must pass)
            self._check_detection_confidence(face, s.LIVENESS_DET_SCORE_MIN),
            self._check_landmark_quality(face, s.LIVENESS_LANDMARK_QUALITY_MIN),
            self._check_skin_tone(face_crop, s),
            self._check_frequency_domain(face_crop, s.LIVENESS_DCT_HIGH_FREQ_MIN),
            self._check_glare(gray_face, s.LIVENESS_GLARE_RATIO_MAX),
            self._check_texture(gray_face, s.LIVENESS_LBP_VARIANCE_MIN),
            self._check_edge_density(
                face_crop, s.LIVENESS_EDGE_DENSITY_MIN,
                s.LIVENESS_EDGE_DENSITY_MAX, s.LIVENESS_EDGE_UNIFORMITY_MAX,
            ),
            self._check_lower_face_visibility(
                face_crop, face, s.LIVENESS_LOWER_FACE_SKIN_MIN,
            ),
            self._check_eye_visibility(
                face_crop, face, s.LIVENESS_EYE_CONTRAST_MIN,
            ),
        ]

        # ML Anti-Spoof check (optional — model trained on limited data,
        # can misclassify real selfies under certain cameras/lighting)
        if self.anti_spoof is not None and s.ANTISPOOF_ENABLED:
            all_checks.append(
                self._check_anti_spoof_model(
                    self.anti_spoof, img, face, s.ANTISPOOF_REAL_SCORE_MIN
                )
            )

        all_checks += [
            # Optional (up to 7 checks — tolerance configurable, default allow 2 failures)
            self._check_noise_level(face_crop, s.LIVENESS_NOISE_LEVEL_MIN),
            self._check_color_correlation(face_crop, s.LIVENESS_COLOR_CORR_MIN),
            self._check_sharpness(gray_face, s.LIVENESS_SHARPNESS_MIN, s.LIVENESS_SHARPNESS_MAX),
            self._check_color_distribution(face_crop, s.LIVENESS_COLOR_STD_MIN),
            self._check_face_size_ratio(bbox, w, h, s.LIVENESS_FACE_SIZE_RATIO_MIN, s.LIVENESS_FACE_SIZE_RATIO_MAX),
            self._check_embedding_quality(face, s.LIVENESS_EMBEDDING_NORM_MIN, s.LIVENESS_EMBEDDING_NORM_MAX),
            self._check_gradient_smoothness(face_crop),
        ]

        # Two-tier verdict
        mandatory = [c for c in all_checks if c.mandatory]
        optional = [c for c in all_checks if not c.mandatory]

        mandatory_passed = sum(1 for c in mandatory if c.passed)
        optional_passed = sum(1 for c in optional if c.passed)

        all_mandatory_ok = mandatory_passed == len(mandatory)
        tolerance = s.LIVENESS_OPTIONAL_TOLERANCE
        optional_ok = optional_passed >= len(optional) - tolerance

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
    # ML Anti-Spoof check (primary gate)
    # ------------------------------------------------------------------

    @staticmethod
    def _check_anti_spoof_model(
        anti_spoof, img: np.ndarray, face, min_real_score: float,
    ) -> CheckResult:
        """Silent-Face-Anti-Spoofing CNN ensemble.

        Two ONNX models (MiniFASNetV2 + MiniFASNetV1SE) classify the face
        as Real (index 1) or Fake (index 0/2). This catches printed photos,
        screen replays, and cartoons that heuristic checks may miss.

        Optional because the model was trained on a limited dataset and
        can misclassify real selfies under certain cameras/lighting.
        """
        try:
            bbox_xyxy = face.bbox.tolist()
            result = anti_spoof.predict(img, bbox_xyxy)
            real_score = result["real_score"]
            passed = result["is_real"] and real_score >= min_real_score

            return CheckResult(
                name="anti_spoof_model",
                passed=passed,
                score=round(real_score, 6),
                detail=(
                    f"ML anti-spoof: {result['label']} "
                    f"(real_score={real_score:.6f}, min={min_real_score}, "
                    f"raw_idx={result['raw_label_idx']})"
                ),
                mandatory=False,
            )
        except Exception as e:
            logger.warning("Anti-spoof model error: %s", e)
            return CheckResult(
                name="anti_spoof_model",
                passed=False,
                score=0.0,
                detail=f"ML anti-spoof model error: {e}",
                mandatory=False,
            )

    # ------------------------------------------------------------------
    # Mandatory heuristic checks (9)
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
    def _check_landmark_quality(face, min_quality: float) -> CheckResult:
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
        sub_total = 5

        # 1. Inter-eye distance ratio (typically 0.28-0.50 of face width)
        eye_dist = float(np.linalg.norm(left_eye - right_eye))
        eye_ratio = eye_dist / face_width
        if 0.28 <= eye_ratio <= 0.50:
            sub_scores += 1.0

        # 2. Nose position: centered between eyes, below eye midpoint
        eye_mid = (left_eye + right_eye) / 2
        nose_x_offset = abs(nose[0] - eye_mid[0]) / face_width
        nose_below = (nose[1] - eye_mid[1]) / face_height
        if nose_x_offset < 0.12 and 0.08 < nose_below < 0.35:
            sub_scores += 1.0

        # 3. Mouth position: below nose, roughly centered
        mouth_mid = (left_mouth + right_mouth) / 2
        mouth_below_nose = (mouth_mid[1] - nose[1]) / face_height
        mouth_centered = abs(mouth_mid[0] - nose[0]) / face_width
        if 0.05 < mouth_below_nose < 0.30 and mouth_centered < 0.10:
            sub_scores += 1.0

        # 4. Face symmetry: nose-to-eye distances should be similar
        dist_nose_left = float(np.linalg.norm(nose - left_eye))
        dist_nose_right = float(np.linalg.norm(nose - right_eye))
        max_nose = max(dist_nose_left, dist_nose_right)
        symmetry = min(dist_nose_left, dist_nose_right) / max_nose if max_nose > 0 else 0
        if symmetry > 0.70:
            sub_scores += 1.0

        # 5. Mouth width vs eye distance (mouth typically 0.8-1.5x eye distance)
        mouth_width = float(np.linalg.norm(left_mouth - right_mouth))
        if eye_dist > 0:
            mouth_eye_ratio = mouth_width / eye_dist
            if 0.7 <= mouth_eye_ratio <= 1.6:
                sub_scores += 1.0

        score = sub_scores / sub_total
        passed = score >= min_quality

        return CheckResult(
            name="landmark_quality",
            passed=passed,
            score=round(score, 4),
            detail=(
                f"Landmark quality: {score:.4f} (min: {min_quality}) "
                f"eye_ratio={eye_ratio:.3f}, symmetry={symmetry:.3f}, "
                f"sub_scores={sub_scores}/{sub_total}"
            ),
            mandatory=True,
        )

    @staticmethod
    def _check_skin_tone(face_crop: np.ndarray, settings) -> CheckResult:
        """Validate realistic skin-toned pixels in HSV space.

        Human skin: H ~0-50 (and 160-180 for red wrap), S 15-200, V 50-255.
        Cartoons have flat fills, non-skin colors, or uniform saturation.
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

        # Check saturation variance of skin pixels
        skin_s_std = 0.0
        flat_fill = False
        if skin_ratio > 0.05:
            skin_s = s_ch[skin_mask > 0]
            if len(skin_s) > 10:
                skin_s_std = float(np.std(skin_s))
                flat_fill = skin_s_std < settings.LIVENESS_SKIN_SAT_STD_MIN
            else:
                flat_fill = True

        passed = skin_ratio >= settings.LIVENESS_SKIN_PIXEL_RATIO_MIN and not flat_fill

        return CheckResult(
            name="skin_tone",
            passed=passed,
            score=round(skin_ratio, 4),
            detail=(
                f"Skin ratio: {skin_ratio:.4f} (min: {settings.LIVENESS_SKIN_PIXEL_RATIO_MIN}), "
                f"sat_std: {skin_s_std:.2f} (min: {settings.LIVENESS_SKIN_SAT_STD_MIN}), "
                f"flat_fill={flat_fill}"
            ),
            mandatory=True,
        )

    @staticmethod
    def _check_frequency_domain(face_crop: np.ndarray, min_ratio: float) -> CheckResult:
        """DCT frequency analysis to detect print/screen recapture attacks.

        Real camera captures have natural high-frequency sensor noise.
        Print/screen recaptures and cartoons lose high-frequency content.
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

    @staticmethod
    def _check_texture(gray_face: np.ndarray, min_variance: float) -> CheckResult:
        """LBP variance — real faces have rich micro-texture.

        Cartoons have flat regions producing low LBP variance.
        Now MANDATORY to catch cartoons.
        """
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
            mandatory=True,
        )

    @staticmethod
    def _check_edge_density(
        face_crop: np.ndarray, min_density: float, max_density: float,
        max_uniformity_std: float = 0.15,
    ) -> CheckResult:
        """Edge density and distribution analysis.

        Real faces: moderate, evenly distributed edges.
        Cartoons: strong outlines with flat interiors (uneven distribution).
        Now MANDATORY to catch cartoons.
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
        not_cartoon_edges = edge_uniformity_std < max_uniformity_std
        passed = density_ok and not_cartoon_edges

        return CheckResult(
            name="edge_density",
            passed=passed,
            score=round(edge_density, 4),
            detail=(
                f"Edge density: {edge_density:.4f} (range: {min_density}-{max_density}), "
                f"uniformity_std: {edge_uniformity_std:.4f} (max: {max_uniformity_std})"
            ),
            mandatory=True,
        )

    @staticmethod
    def _check_lower_face_visibility(
        face_crop: np.ndarray, face, min_skin_ratio: float,
    ) -> CheckResult:
        """Detect face masks by checking skin-colored pixels in the lower face.

        Splits the face crop into upper and lower halves. The lower half
        (nose, mouth, chin) should contain visible skin. Face masks
        (medical, cloth, N95) cover this region, producing very low
        skin pixel ratios in the lower half.

        Uses the nose landmark as the split point when available.
        """
        h, w = face_crop.shape[:2]
        if h < 20 or w < 20:
            return CheckResult(
                name="lower_face_visibility", passed=False, score=0.0,
                detail="Face crop too small for occlusion check", mandatory=True,
            )

        # Use nose landmark to find the split point
        split_y = h // 2
        if hasattr(face, "kps") and face.kps is not None:
            bbox = face.bbox.astype(int)
            nose = face.kps[2]  # nose tip
            # Convert nose Y from image coords to face_crop coords
            nose_y_in_crop = int(nose[1]) - max(0, bbox[1])
            if 0 < nose_y_in_crop < h:
                split_y = nose_y_in_crop

        lower_face = face_crop[split_y:, :, :]

        # Check skin pixels in lower face using HSV
        hsv = cv2.cvtColor(lower_face, cv2.COLOR_BGR2HSV)
        lower1 = np.array([0, 10, 50], dtype=np.uint8)
        upper1 = np.array([50, 220, 255], dtype=np.uint8)
        mask1 = cv2.inRange(hsv, lower1, upper1)

        lower2 = np.array([160, 10, 50], dtype=np.uint8)
        upper2 = np.array([180, 220, 255], dtype=np.uint8)
        mask2 = cv2.inRange(hsv, lower2, upper2)

        skin_mask = cv2.bitwise_or(mask1, mask2)
        total_pixels = skin_mask.size
        skin_ratio = float(np.count_nonzero(skin_mask)) / total_pixels if total_pixels > 0 else 0.0

        passed = skin_ratio >= min_skin_ratio

        return CheckResult(
            name="lower_face_visibility",
            passed=passed,
            score=round(skin_ratio, 4),
            detail=(
                f"Lower face skin ratio: {skin_ratio:.4f} (min: {min_skin_ratio}). "
                f"Low values indicate face mask or covering"
            ),
            mandatory=True,
        )

    @staticmethod
    def _check_eye_visibility(
        face_crop: np.ndarray, face, min_contrast: float,
    ) -> CheckResult:
        """Detect sunglasses by analyzing gradient contrast in eye regions.

        Extracts small patches around each eye landmark and measures
        gradient magnitude (Sobel). Real uncovered eyes have rich
        gradients from iris, pupil, eyelid edges. Sunglasses produce
        uniformly dark regions with very low gradient contrast.
        """
        if not hasattr(face, "kps") or face.kps is None:
            return CheckResult(
                name="eye_visibility", passed=False, score=0.0,
                detail="No landmarks for eye visibility check", mandatory=True,
            )

        h, w = face_crop.shape[:2]
        bbox = face.bbox.astype(int)
        x_off = max(0, bbox[0])
        y_off = max(0, bbox[1])

        left_eye = face.kps[0]
        right_eye = face.kps[1]

        # Eye patch size: ~12% of face width
        eye_dist = float(np.linalg.norm(left_eye - right_eye))
        patch_r = max(8, int(eye_dist * 0.25))

        eye_contrasts = []
        for eye in [left_eye, right_eye]:
            # Convert to face_crop coords
            ex = int(eye[0]) - x_off
            ey = int(eye[1]) - y_off

            # Clamp to crop bounds
            y1 = max(0, ey - patch_r)
            y2 = min(h, ey + patch_r)
            x1 = max(0, ex - patch_r)
            x2 = min(w, ex + patch_r)

            if y2 - y1 < 5 or x2 - x1 < 5:
                eye_contrasts.append(0.0)
                continue

            patch = face_crop[y1:y2, x1:x2]
            gray_patch = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)

            # Sobel gradient magnitude
            gx = cv2.Sobel(gray_patch, cv2.CV_64F, 1, 0, ksize=3)
            gy = cv2.Sobel(gray_patch, cv2.CV_64F, 0, 1, ksize=3)
            mag = np.sqrt(gx ** 2 + gy ** 2)
            eye_contrasts.append(float(np.mean(mag)))

        avg_contrast = float(np.mean(eye_contrasts)) if eye_contrasts else 0.0
        passed = avg_contrast >= min_contrast

        return CheckResult(
            name="eye_visibility",
            passed=passed,
            score=round(avg_contrast, 2),
            detail=(
                f"Eye region gradient: {avg_contrast:.2f} (min: {min_contrast}). "
                f"Left: {eye_contrasts[0]:.2f}, Right: {eye_contrasts[1]:.2f}. "
                f"Low values indicate sunglasses or eye covering"
            ),
            mandatory=True,
        )

    @staticmethod
    def _check_noise_level(face_crop: np.ndarray, min_noise: float) -> CheckResult:
        """Camera noise pattern analysis.

        Real camera images always contain sensor noise visible as small
        differences between the original and a median-filtered version.
        Cartoons and digital art have zero sensor noise.
        JPEG compression can reduce noise in real photos, so this is optional.
        """
        gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
        resized = cv2.resize(gray, (128, 128))

        # Median filter removes noise but preserves edges
        filtered = cv2.medianBlur(resized, 3)

        # Noise = difference between original and filtered
        diff = np.abs(resized.astype(np.float64) - filtered.astype(np.float64))
        noise_level = float(np.mean(diff))

        passed = noise_level >= min_noise

        return CheckResult(
            name="noise_pattern",
            passed=passed,
            score=round(noise_level, 4),
            detail=f"Camera noise level: {noise_level:.4f} (min: {min_noise})",
            mandatory=False,
        )

    @staticmethod
    def _check_color_correlation(face_crop: np.ndarray, min_corr: float) -> CheckResult:
        """Color channel correlation analysis.

        In real photos under natural/artificial lighting, R, G, B channels
        are highly correlated (skin tones, shadows follow physics).
        Cartoons use independent flat color fills with low inter-channel
        correlation. Optional because diverse skin tones and lighting
        conditions can produce lower correlation in real photos.
        """
        if face_crop.shape[0] < 10 or face_crop.shape[1] < 10:
            return CheckResult(
                name="color_correlation", passed=False, score=0.0,
                detail="Face crop too small", mandatory=False,
            )

        b, g, r = cv2.split(face_crop)
        b_flat = b.flatten().astype(np.float64)
        g_flat = g.flatten().astype(np.float64)
        r_flat = r.flatten().astype(np.float64)

        # Compute pairwise Pearson correlation
        correlations = []
        for ch_a, ch_b in [(r_flat, g_flat), (r_flat, b_flat), (g_flat, b_flat)]:
            std_a = np.std(ch_a)
            std_b = np.std(ch_b)
            if std_a > 0 and std_b > 0:
                corr = float(np.corrcoef(ch_a, ch_b)[0, 1])
                correlations.append(corr)
            else:
                correlations.append(0.0)

        avg_corr = float(np.mean(correlations)) if correlations else 0.0
        passed = avg_corr >= min_corr

        return CheckResult(
            name="color_correlation",
            passed=passed,
            score=round(avg_corr, 4),
            detail=(
                f"Avg channel correlation: {avg_corr:.4f} (min: {min_corr}), "
                f"R-G: {correlations[0]:.4f}, R-B: {correlations[1]:.4f}, G-B: {correlations[2]:.4f}"
            ),
            mandatory=False,
        )

    # ------------------------------------------------------------------
    # Optional checks (7)
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
    def _check_gradient_smoothness(face_crop: np.ndarray) -> CheckResult:
        """Detect AI-generated images via gradient analysis.

        AI-generated faces (Midjourney, DALL-E, Stable Diffusion) produce
        unnaturally smooth gradients in skin regions. Real camera photos
        have micro-texture, sensor noise, and compression artifacts that
        create higher gradient variance even in smooth-looking areas.

        Measures the standard deviation of gradient magnitudes in the face
        crop — real photos have higher variance, AI images are too clean.
        """
        gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
        resized = cv2.resize(gray, (128, 128))

        # Sobel gradients
        grad_x = cv2.Sobel(resized, cv2.CV_64F, 1, 0, ksize=3)
        grad_y = cv2.Sobel(resized, cv2.CV_64F, 0, 1, ksize=3)
        magnitude = np.sqrt(grad_x ** 2 + grad_y ** 2)

        # Gradient magnitude stats
        grad_mean = float(np.mean(magnitude))
        grad_std = float(np.std(magnitude))

        # Coefficient of variation: std/mean — measures gradient irregularity
        # Real photos: higher CoV (noisy, irregular gradients)
        # AI images: lower CoV (smooth, uniform gradients)
        cov = grad_std / max(grad_mean, 0.001)

        # Also check: ratio of low-gradient pixels (< 5.0)
        # AI images have more ultra-smooth patches
        smooth_ratio = float(np.mean(magnitude < 5.0))

        # Real photos: cov > 1.0 and smooth_ratio < 0.70
        # AI images: cov ≈ 0.8-1.0 and smooth_ratio > 0.70
        passed = cov >= 0.95 and smooth_ratio <= 0.75

        return CheckResult(
            name="gradient_smoothness",
            passed=passed,
            score=round(cov, 4),
            detail=(
                f"Gradient CoV: {cov:.4f} (min: 0.95), "
                f"smooth_ratio: {smooth_ratio:.4f} (max: 0.75), "
                f"grad_mean: {grad_mean:.2f}, grad_std: {grad_std:.2f}"
            ),
            mandatory=False,
        )
