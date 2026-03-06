import logging
from typing import NamedTuple

import cv2
import numpy as np
from insightface.app import FaceAnalysis

from app.config import get_settings
from app.core.exceptions import InsufficientFramesError, NoFaceDetectedError
from app.services.face_service import FaceService
from app.services.liveness_service import LivenessService

logger = logging.getLogger(__name__)


class InterFrameCheckResult(NamedTuple):
    name: str
    passed: bool
    score: float
    detail: str
    mandatory: bool


class MultiFrameLivenessService:
    """Multi-frame active liveness detection.

    Requires 3-5 sequential image frames. Runs:
      1. Per-frame passive liveness checks (11 checks each, via LivenessService)
      2. Inter-frame active checks (5 checks):
         - Identity consistency (same person across frames)
         - Landmark displacement (real facial movement)
         - Head pose variation (not a flat surface)
         - Optical flow analysis (pixel-level motion)
         - Bounding box natural shift (micro-sway)

    A static image (cartoon, printed photo, screen replay) cannot produce
    genuine inter-frame motion and will fail the active checks.
    """

    def __init__(self, analyzer: FaceAnalysis):
        self.analyzer = analyzer
        self._settings = get_settings()
        self._liveness_svc = LivenessService(analyzer)
        self._face_svc = FaceService(analyzer)
        self._primary_frame_data: tuple | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_multi_frame_liveness(self, frames: list[bytes]) -> dict:
        """Run multi-frame liveness on raw image bytes.

        Args:
            frames: List of 3-5 image byte arrays captured in sequence.

        Returns:
            Dict with is_live verdict, passive/active check details.
        """
        s = self._settings

        if len(frames) < s.MULTIFRAME_MIN_FRAMES:
            raise InsufficientFramesError(
                f"Need at least {s.MULTIFRAME_MIN_FRAMES} frames, got {len(frames)}"
            )
        if len(frames) > s.MULTIFRAME_MAX_FRAMES:
            raise InsufficientFramesError(
                f"Maximum {s.MULTIFRAME_MAX_FRAMES} frames, got {len(frames)}"
            )

        # Detect face in each frame
        frame_data = []
        for i, frame_bytes in enumerate(frames):
            try:
                img, face, face_crop = self._face_svc.detect_face(frame_bytes)
                frame_data.append((img, face, face_crop))
            except NoFaceDetectedError:
                raise NoFaceDetectedError(f"No face detected in frame {i}")

        return self.check_multi_frame_liveness_from_faces(frame_data)

    def check_multi_frame_liveness_from_faces(
        self,
        frame_data: list[tuple[np.ndarray, object, np.ndarray]],
    ) -> dict:
        """Run multi-frame liveness on pre-detected faces.

        Use when faces are already detected (e.g. enrollment flow).

        Args:
            frame_data: List of (img_array, face_object, face_crop) tuples.
        """
        s = self._settings

        # Store first frame for embedding extraction
        self._primary_frame_data = frame_data[0]

        images = [fd[0] for fd in frame_data]
        faces = [fd[1] for fd in frame_data]
        face_crops = [fd[2] for fd in frame_data]

        # ----------------------------------------------------------
        # Step 1: Per-frame passive liveness checks
        # ----------------------------------------------------------
        passive_results = []
        all_passive_passed = True

        for i, (img, face, face_crop) in enumerate(frame_data):
            result = self._liveness_svc.check_liveness_from_face(img, face, face_crop)
            passive_results.append({
                "frame_index": i,
                "is_live": result["is_live"],
                "liveness_score": result["liveness_score"],
                "checks_passed": result["checks_passed"],
                "checks_total": result["checks_total"],
            })
            if not result["is_live"]:
                all_passive_passed = False

        # ----------------------------------------------------------
        # Step 2: Inter-frame active checks (5 mandatory)
        # ----------------------------------------------------------
        active_checks = [
            self._check_identity_consistency(
                faces, s.MULTIFRAME_IDENTITY_SIM_MIN,
            ),
            self._check_landmark_displacement(
                faces, s.MULTIFRAME_LANDMARK_DISP_MIN, s.MULTIFRAME_LANDMARK_DISP_MAX,
            ),
            self._check_head_pose_variation(
                faces,
                s.MULTIFRAME_POSE_RANGE_MIN,
                s.MULTIFRAME_POSE_COMBINED_MIN,
                s.MULTIFRAME_POSE_ASYMMETRY_RANGE_MIN,
            ),
            self._check_optical_flow(
                images, faces,
                s.MULTIFRAME_FLOW_MAG_MIN,
                s.MULTIFRAME_FLOW_MAG_MAX,
                s.MULTIFRAME_FLOW_DIR_STD_MIN,
            ),
            self._check_bbox_shift(
                faces,
                [(img.shape[0], img.shape[1]) for img in images],
                s.MULTIFRAME_BBOX_SHIFT_STD_MIN,
                s.MULTIFRAME_BBOX_SHIFT_MAX,
            ),
        ]

        active_passed = sum(1 for c in active_checks if c.passed)
        all_active_passed = active_passed == len(active_checks)

        # Build active checks dict
        active_checks_dict = {}
        for c in active_checks:
            active_checks_dict[c.name] = {
                "score": c.score,
                "passed": c.passed,
                "detail": c.detail,
                "mandatory": c.mandatory,
            }

        # ----------------------------------------------------------
        # Step 3: Combined verdict
        # ----------------------------------------------------------
        is_live = all_passive_passed and all_active_passed

        # Score: weighted average (passive 40%, active 60%)
        mean_passive_score = (
            sum(r["liveness_score"] for r in passive_results) / len(passive_results)
            if passive_results else 0.0
        )
        active_score = active_passed / len(active_checks) if active_checks else 0.0
        liveness_score = mean_passive_score * 0.4 + active_score * 0.6

        face_info = FaceService.extract_face_info(faces[0])

        logger.info(
            "Multi-frame liveness: frames=%d passive_ok=%s active=%d/%d live=%s score=%.2f",
            len(frame_data), all_passive_passed,
            active_passed, len(active_checks),
            is_live, liveness_score,
        )

        return {
            "is_live": is_live,
            "liveness_score": round(liveness_score, 4),
            "mode": "multi_frame",
            "frame_count": len(frame_data),
            "passive_checks": {
                "all_passed": all_passive_passed,
                "per_frame": passive_results,
            },
            "active_checks": {
                "checks_passed": active_passed,
                "checks_total": len(active_checks),
                "all_passed": all_active_passed,
                "checks": active_checks_dict,
            },
            "face_info": face_info,
        }

    def get_primary_frame_data(self) -> tuple[np.ndarray, object, np.ndarray]:
        """Return the first frame's (img, face, face_crop) for embedding.

        Must be called after check_multi_frame_liveness* methods.
        """
        if self._primary_frame_data is None:
            raise RuntimeError("No multi-frame check has been run yet")
        return self._primary_frame_data

    # ------------------------------------------------------------------
    # Inter-frame active checks
    # ------------------------------------------------------------------

    @staticmethod
    def _check_identity_consistency(
        faces: list, min_similarity: float,
    ) -> InterFrameCheckResult:
        """Verify all frames show the same person.

        Computes cosine similarity between consecutive embedding pairs
        and first-to-last pair. Prevents multi-person frame splicing.
        """
        embeddings = [f.normed_embedding for f in faces]
        similarities = []

        # Consecutive pairs
        for i in range(len(embeddings) - 1):
            sim = float(np.dot(embeddings[i], embeddings[i + 1]))
            similarities.append(sim)

        # First-to-last (catch drift)
        if len(embeddings) > 2:
            sim_fl = float(np.dot(embeddings[0], embeddings[-1]))
            similarities.append(sim_fl)

        min_sim = min(similarities) if similarities else 0.0
        passed = min_sim >= min_similarity

        return InterFrameCheckResult(
            name="identity_consistency",
            passed=passed,
            score=round(min_sim, 4),
            detail=(
                f"Min pairwise similarity: {min_sim:.4f} (min: {min_similarity}), "
                f"all pairs: {[round(s, 4) for s in similarities]}"
            ),
            mandatory=True,
        )

    @staticmethod
    def _check_landmark_displacement(
        faces: list, min_disp: float, max_disp: float,
    ) -> InterFrameCheckResult:
        """Detect genuine facial movement via landmark shifts.

        Normalizes 5-point landmarks to bbox coordinates, then computes
        mean Euclidean displacement between consecutive frames.
        A static image produces near-zero displacement.
        """
        displacements = []

        for i in range(len(faces) - 1):
            kps_a = faces[i].kps
            kps_b = faces[i + 1].kps
            bbox_a = faces[i].bbox
            bbox_b = faces[i + 1].bbox

            # Normalize landmarks to [0, 1] relative to bbox
            w_a = max(bbox_a[2] - bbox_a[0], 1.0)
            h_a = max(bbox_a[3] - bbox_a[1], 1.0)
            w_b = max(bbox_b[2] - bbox_b[0], 1.0)
            h_b = max(bbox_b[3] - bbox_b[1], 1.0)

            norm_a = (kps_a - bbox_a[:2]) / np.array([w_a, h_a])
            norm_b = (kps_b - bbox_b[:2]) / np.array([w_b, h_b])

            frame_disp = float(np.mean(np.linalg.norm(norm_b - norm_a, axis=1)))
            displacements.append(frame_disp)

        mean_disp = float(np.mean(displacements)) if displacements else 0.0
        passed = min_disp <= mean_disp <= max_disp

        return InterFrameCheckResult(
            name="landmark_displacement",
            passed=passed,
            score=round(mean_disp, 6),
            detail=(
                f"Mean normalized landmark displacement: {mean_disp:.6f} "
                f"(range: {min_disp}-{max_disp}), "
                f"per-pair: {[round(d, 6) for d in displacements]}"
            ),
            mandatory=True,
        )

    @staticmethod
    def _check_head_pose_variation(
        faces: list,
        pose_range_min: float,
        pose_combined_min: float,
        asymmetry_range_min: float,
    ) -> InterFrameCheckResult:
        """Verify head pose varies between frames.

        Uses face.pose [pitch, yaw, roll] if available.
        Falls back to landmark-based yaw approximation.
        A flat surface (printed photo, screen) shows near-zero pose variation.
        """
        # Try face.pose first
        poses = []
        use_pose_attr = True
        for f in faces:
            if hasattr(f, "pose") and f.pose is not None:
                try:
                    p = np.array(f.pose, dtype=float)
                    if p.shape == (3,):
                        poses.append(p)
                    else:
                        use_pose_attr = False
                        break
                except (ValueError, TypeError):
                    use_pose_attr = False
                    break
            else:
                use_pose_attr = False
                break

        if use_pose_attr and len(poses) == len(faces):
            poses_arr = np.array(poses)  # shape (N, 3) for pitch, yaw, roll
            ranges = np.ptp(poses_arr, axis=0)
            max_range = float(np.max(ranges))
            combined = float(np.sum(ranges))
            passed = max_range >= pose_range_min and combined >= pose_combined_min

            return InterFrameCheckResult(
                name="head_pose_variation",
                passed=passed,
                score=round(combined, 4),
                detail=(
                    f"Pose ranges [pitch, yaw, roll]: "
                    f"{[round(float(r), 4) for r in ranges]}, "
                    f"combined: {combined:.4f} "
                    f"(min single: {pose_range_min}, min combined: {pose_combined_min})"
                ),
                mandatory=True,
            )

        # Fallback: landmark-based yaw approximation
        asymmetries = []
        for f in faces:
            kps = f.kps
            left_eye, right_eye, nose = kps[0], kps[1], kps[2]
            eye_mid_x = (left_eye[0] + right_eye[0]) / 2.0
            ied = float(np.linalg.norm(left_eye - right_eye))
            if ied > 0:
                asym = (nose[0] - eye_mid_x) / ied
            else:
                asym = 0.0
            asymmetries.append(asym)

        asym_range = float(np.ptp(asymmetries))
        passed = asym_range >= asymmetry_range_min

        return InterFrameCheckResult(
            name="head_pose_variation",
            passed=passed,
            score=round(asym_range, 6),
            detail=(
                f"Landmark asymmetry range: {asym_range:.6f} "
                f"(min: {asymmetry_range_min}), "
                f"values: {[round(a, 4) for a in asymmetries]} "
                f"(pose attr unavailable, using landmark fallback)"
            ),
            mandatory=True,
        )

    @staticmethod
    def _check_optical_flow(
        images: list[np.ndarray],
        faces: list,
        flow_mag_min: float,
        flow_mag_max: float,
        flow_dir_std_min: float,
    ) -> InterFrameCheckResult:
        """Verify pixel-level motion between consecutive frames.

        Uses Farneback dense optical flow on 128x128 face crops.
        Real faces produce moderate flow with varied direction (3D surface).
        Static images produce either zero flow or uniform translational flow.
        """
        target_size = (128, 128)
        magnitudes = []
        dir_stds = []

        for i in range(len(images) - 1):
            bbox_a = faces[i].bbox.astype(int)
            bbox_b = faces[i + 1].bbox.astype(int)

            h_a, w_a = images[i].shape[:2]
            h_b, w_b = images[i + 1].shape[:2]

            crop_a = images[i][
                max(0, bbox_a[1]):min(h_a, bbox_a[3]),
                max(0, bbox_a[0]):min(w_a, bbox_a[2]),
            ]
            crop_b = images[i + 1][
                max(0, bbox_b[1]):min(h_b, bbox_b[3]),
                max(0, bbox_b[0]):min(w_b, bbox_b[2]),
            ]

            # Skip if crops are too small
            if crop_a.size == 0 or crop_b.size == 0:
                magnitudes.append(0.0)
                dir_stds.append(0.0)
                continue

            gray_a = cv2.cvtColor(
                cv2.resize(crop_a, target_size), cv2.COLOR_BGR2GRAY
            )
            gray_b = cv2.cvtColor(
                cv2.resize(crop_b, target_size), cv2.COLOR_BGR2GRAY
            )

            flow = cv2.calcOpticalFlowFarneback(
                gray_a, gray_b, None,
                pyr_scale=0.5, levels=3, winsize=15,
                iterations=3, poly_n=5, poly_sigma=1.2, flags=0,
            )

            mag, ang = cv2.cartToPolar(flow[..., 0], flow[..., 1])
            mean_mag = float(np.mean(mag))

            # Direction std: only for pixels with meaningful flow
            meaningful = mag > 0.1
            if np.any(meaningful):
                dir_std = float(np.std(ang[meaningful]))
            else:
                dir_std = 0.0

            magnitudes.append(mean_mag)
            dir_stds.append(dir_std)

        avg_mag = float(np.mean(magnitudes)) if magnitudes else 0.0
        avg_dir_std = float(np.mean(dir_stds)) if dir_stds else 0.0

        mag_ok = flow_mag_min <= avg_mag <= flow_mag_max
        dir_ok = avg_dir_std >= flow_dir_std_min
        passed = mag_ok and dir_ok

        return InterFrameCheckResult(
            name="optical_flow",
            passed=passed,
            score=round(avg_mag, 4),
            detail=(
                f"Avg flow magnitude: {avg_mag:.4f} "
                f"(range: {flow_mag_min}-{flow_mag_max}), "
                f"avg direction std: {avg_dir_std:.4f} "
                f"(min: {flow_dir_std_min}), "
                f"per-pair mag: {[round(m, 4) for m in magnitudes]}"
            ),
            mandatory=True,
        )

    @staticmethod
    def _check_bbox_shift(
        faces: list,
        image_shapes: list[tuple[int, int]],
        shift_std_min: float,
        shift_max: float,
    ) -> InterFrameCheckResult:
        """Verify natural micro-sway of face position between frames.

        Even when holding still, a live person's face shifts slightly.
        A perfectly static image does not shift at all.
        """
        centers = []
        for face, (h, w) in zip(faces, image_shapes):
            bbox = face.bbox
            cx = (bbox[0] + bbox[2]) / 2.0 / max(w, 1)
            cy = (bbox[1] + bbox[3]) / 2.0 / max(h, 1)
            centers.append(np.array([cx, cy]))

        centers_arr = np.array(centers)
        center_std = float(np.mean(np.std(centers_arr, axis=0)))

        # Max displacement between consecutive frames
        max_disp = 0.0
        displacements = []
        for i in range(len(centers_arr) - 1):
            disp = float(np.linalg.norm(centers_arr[i + 1] - centers_arr[i]))
            displacements.append(disp)
            max_disp = max(max_disp, disp)

        std_ok = center_std >= shift_std_min
        max_ok = max_disp <= shift_max
        passed = std_ok and max_ok

        return InterFrameCheckResult(
            name="bbox_shift",
            passed=passed,
            score=round(center_std, 6),
            detail=(
                f"Bbox center std: {center_std:.6f} (min: {shift_std_min}), "
                f"max displacement: {max_disp:.6f} (max: {shift_max}), "
                f"per-pair: {[round(d, 6) for d in displacements]}"
            ),
            mandatory=True,
        )
