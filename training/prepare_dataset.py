#!/usr/bin/env python3
"""Prepare training dataset from raw face images.

Takes a directory of face images organized by class and generates
multi-scale face crops for training the anti-spoof models.

Usage:
    python prepare_dataset.py \
        --input-dir ./raw_data \
        --output-dir ./datasets \
        --scales 2.7 4.0

Input structure:
    raw_data/
        0/  (real faces - live selfies)
        1/  (spoof - printed photo attacks)
        2/  (spoof - screen replay attacks)

Output structure:
    datasets/
        2.7_80x80/
            train/  0/, 1/, 2/
            val/    0/, 1/, 2/
        4.0_80x80/
            train/  0/, 1/, 2/
            val/    0/, 1/, 2/
"""

import argparse
import os
import random
import sys

import cv2
import numpy as np
from insightface.app import FaceAnalysis


def crop_face(image, bbox, scale, out_size=(80, 80)):
    """Crop face region with scale expansion around bbox center.

    Args:
        image:    Full image (numpy BGR array)
        bbox:     Face bounding box [x1, y1, x2, y2]
        scale:    Expansion factor (1.0 = tight crop, 4.0 = wide context)
        out_size: Output dimensions (width, height)

    Returns:
        Cropped and resized face patch (numpy BGR array)
    """
    h, w = image.shape[:2]
    x1, y1, x2, y2 = bbox

    # Center and size
    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2
    face_w = x2 - x1
    face_h = y2 - y1

    # Expand by scale factor
    new_w = face_w * scale
    new_h = face_h * scale

    # New bounding box
    nx1 = max(0, int(cx - new_w / 2))
    ny1 = max(0, int(cy - new_h / 2))
    nx2 = min(w, int(cx + new_w / 2))
    ny2 = min(h, int(cy + new_h / 2))

    crop = image[ny1:ny2, nx1:nx2]

    if crop.size == 0:
        return None

    resized = cv2.resize(crop, out_size, interpolation=cv2.INTER_LINEAR)
    return resized


def process_directory(input_dir, output_dir, face_app, scales, out_size,
                      val_split, seed):
    """Process all images in input_dir and generate multi-scale crops."""
    random.seed(seed)

    classes = sorted(
        d for d in os.listdir(input_dir)
        if os.path.isdir(os.path.join(input_dir, d))
    )

    if not classes:
        print(f"ERROR: No class directories found in {input_dir}")
        print("Expected structure: input_dir/0/, input_dir/1/, input_dir/2/")
        sys.exit(1)

    print(f"Found classes: {classes}")

    for scale in scales:
        scale_name = f"{scale}_80x80"
        for split in ["train", "val"]:
            for cls in classes:
                os.makedirs(
                    os.path.join(output_dir, scale_name, split, cls),
                    exist_ok=True,
                )

    stats = {"total": 0, "faces_found": 0, "no_face": 0}

    for cls in classes:
        cls_dir = os.path.join(input_dir, cls)
        files = sorted(
            f for f in os.listdir(cls_dir)
            if f.lower().rsplit(".", 1)[-1] in {"jpg", "jpeg", "png", "bmp", "webp"}
        )

        random.shuffle(files)
        split_idx = int(len(files) * (1.0 - val_split))
        train_files = files[:split_idx]
        val_files = files[split_idx:]

        for split_name, split_files in [("train", train_files), ("val", val_files)]:
            for fname in split_files:
                fpath = os.path.join(cls_dir, fname)
                stats["total"] += 1

                image = cv2.imread(fpath)
                if image is None:
                    print(f"  WARN: Could not read {fpath}")
                    continue

                # Detect face
                faces = face_app.get(image)
                if not faces:
                    stats["no_face"] += 1
                    if stats["no_face"] <= 10:
                        print(f"  WARN: No face in {fpath}")
                    continue

                face = faces[0]
                bbox = face.bbox.astype(int).tolist()
                stats["faces_found"] += 1

                # Generate crops at each scale
                for scale in scales:
                    crop = crop_face(image, bbox, scale, out_size)
                    if crop is None:
                        continue

                    scale_name = f"{scale}_80x80"
                    out_path = os.path.join(
                        output_dir, scale_name, split_name, cls,
                        fname.rsplit(".", 1)[0] + ".png",
                    )
                    cv2.imwrite(out_path, crop)

                if stats["faces_found"] % 100 == 0:
                    print(
                        f"  Processed {stats['faces_found']} faces "
                        f"({stats['total']} total, {stats['no_face']} no-face)"
                    )

    print(f"\nDone! {stats['faces_found']} faces processed, "
          f"{stats['no_face']} skipped (no face detected)")

    # Print dataset summary
    for scale in scales:
        scale_name = f"{scale}_80x80"
        for split in ["train", "val"]:
            for cls in classes:
                d = os.path.join(output_dir, scale_name, split, cls)
                count = len(os.listdir(d)) if os.path.exists(d) else 0
                print(f"  {scale_name}/{split}/{cls}: {count} images")


def main():
    parser = argparse.ArgumentParser(
        description="Prepare multi-scale face crops for anti-spoof training"
    )
    parser.add_argument(
        "--input-dir", required=True,
        help="Input directory with class subdirs (0/, 1/, 2/)",
    )
    parser.add_argument(
        "--output-dir", default="./datasets",
        help="Output directory for processed datasets (default: ./datasets)",
    )
    parser.add_argument(
        "--scales", nargs="+", type=float, default=[2.7, 4.0],
        help="Scale factors for face crops (default: 2.7 4.0)",
    )
    parser.add_argument(
        "--size", type=int, default=80,
        help="Output crop size (default: 80 → 80x80)",
    )
    parser.add_argument(
        "--val-split", type=float, default=0.15,
        help="Fraction of data for validation (default: 0.15)",
    )
    parser.add_argument(
        "--det-size", type=int, default=640,
        help="Face detection input size (default: 640)",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for train/val split (default: 42)",
    )
    args = parser.parse_args()

    out_size = (args.size, args.size)

    print("Initializing face detector (InsightFace)...")
    face_app = FaceAnalysis(
        name="buffalo_l",
        providers=["CPUExecutionProvider"],
    )
    face_app.prepare(ctx_id=0, det_size=(args.det_size, args.det_size))

    print(f"Processing images from: {args.input_dir}")
    print(f"Scales: {args.scales}")
    print(f"Output: {args.output_dir}")
    print(f"Val split: {args.val_split}")
    print()

    process_directory(
        args.input_dir, args.output_dir, face_app,
        args.scales, out_size, args.val_split, args.seed,
    )


if __name__ == "__main__":
    main()
