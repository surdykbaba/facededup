#!/usr/bin/env python3
"""Evaluate anti-spoof model performance.

Computes standard face anti-spoofing metrics:
- APCER (Attack Presentation Classification Error Rate)
- BPCER (Bona Fide Presentation Classification Error Rate)
- ACER  (Average Classification Error Rate)
- AUC   (Area Under ROC Curve)
- Per-class accuracy

Usage:
    # Evaluate single model
    python evaluate.py \
        --model V2 \
        --weights ./checkpoints/V2_2.7_80x80_best.pth \
        --data-dir ./datasets/2.7_80x80/val

    # Evaluate ONNX model
    python evaluate.py \
        --onnx ../app/models/anti_spoof/MiniFASNetV2.onnx \
        --data-dir ./datasets/2.7_80x80/val

    # Evaluate 2-model ensemble (production config)
    python evaluate.py \
        --model V2 --weights ./checkpoints/V2_2.7_80x80_best.pth \
        --model2 V1SE --weights2 ./checkpoints/V1SE_4.0_80x80_best.pth \
        --data-dir ./datasets/2.7_80x80/val \
        --data-dir2 ./datasets/4.0_80x80/val
"""

import argparse
import os
from collections import OrderedDict

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from torchvision import transforms

from src.model_lib.MiniFASNet import (
    MiniFASNetV1,
    MiniFASNetV1SE,
    MiniFASNetV2,
    MiniFASNetV2SE,
    get_kernel,
)

MODEL_MAP = {
    "V1": MiniFASNetV1,
    "V2": MiniFASNetV2,
    "V1SE": MiniFASNetV1SE,
    "V2SE": MiniFASNetV2SE,
}


def load_model(model_name, weights_path, input_size=80, num_classes=3):
    """Load a PyTorch model with weights."""
    kernel = get_kernel(input_size, input_size)
    model = MODEL_MAP[model_name](conv6_kernel=kernel, num_classes=num_classes)

    state_dict = torch.load(weights_path, map_location="cpu", weights_only=True)
    cleaned = OrderedDict()
    for k, v in state_dict.items():
        name = k.replace("module.", "").replace("backbone.", "")
        cleaned[name] = v

    model_keys = set(model.state_dict().keys())
    filtered = OrderedDict((k, v) for k, v in cleaned.items() if k in model_keys)
    model.load_state_dict(filtered, strict=False)
    model.eval()
    return model


def get_samples(data_dir):
    """Get all image samples from a class-organized directory."""
    samples = []
    for class_name in sorted(os.listdir(data_dir)):
        class_dir = os.path.join(data_dir, class_name)
        if not os.path.isdir(class_dir):
            continue
        try:
            class_idx = int(class_name)
        except ValueError:
            continue
        for fname in sorted(os.listdir(class_dir)):
            fpath = os.path.join(class_dir, fname)
            ext = fname.lower().rsplit(".", 1)[-1] if "." in fname else ""
            if ext in {"jpg", "jpeg", "png", "bmp", "webp"}:
                samples.append((fpath, class_idx))
    return samples


def predict_pytorch(model, image_path, input_size=80):
    """Run prediction with PyTorch model."""
    image = cv2.imread(image_path)
    if image is None:
        return None
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    transform = transforms.Compose([
        transforms.ToPILImage(),
        transforms.Resize((input_size, input_size)),
        transforms.ToTensor(),
    ])
    tensor = transform(image_rgb).unsqueeze(0)
    with torch.no_grad():
        output = model(tensor)
        probs = F.softmax(output, dim=1)
    return probs.numpy()[0]


def predict_onnx(session, image_path, input_size=80):
    """Run prediction with ONNX Runtime model."""
    image = cv2.imread(image_path)
    if image is None:
        return None
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    transform = transforms.Compose([
        transforms.ToPILImage(),
        transforms.Resize((input_size, input_size)),
        transforms.ToTensor(),
    ])
    tensor = transform(image_rgb).unsqueeze(0).numpy()
    output = session.run(None, {"input": tensor})[0]
    # Softmax
    exp = np.exp(output - np.max(output, axis=1, keepdims=True))
    probs = exp / exp.sum(axis=1, keepdims=True)
    return probs[0]


def compute_metrics(labels, real_scores, threshold=0.5):
    """Compute APCER, BPCER, ACER at given threshold."""
    labels = np.array(labels)
    real_scores = np.array(real_scores)

    # Real = class 0, Spoof = class 1 or 2
    is_real = labels == 0
    is_spoof = ~is_real

    predicted_real = real_scores >= threshold

    # BPCER: fraction of real faces classified as spoof
    real_count = is_real.sum()
    bpcer = 0.0
    if real_count > 0:
        bpcer = (is_real & ~predicted_real).sum() / real_count

    # APCER: fraction of spoofs classified as real
    spoof_count = is_spoof.sum()
    apcer = 0.0
    if spoof_count > 0:
        apcer = (is_spoof & predicted_real).sum() / spoof_count

    # ACER: average of APCER and BPCER
    acer = (apcer + bpcer) / 2

    return apcer, bpcer, acer


def compute_auc(labels, real_scores):
    """Compute AUC using trapezoidal rule."""
    labels = np.array(labels)
    real_scores = np.array(real_scores)

    is_real = labels == 0

    thresholds = np.linspace(0, 1, 200)
    tpr_list = []
    fpr_list = []

    for t in thresholds:
        predicted_real = real_scores >= t

        # TPR = real correctly classified as real
        real_count = is_real.sum()
        tpr = (is_real & predicted_real).sum() / max(real_count, 1)

        # FPR = spoof misclassified as real
        spoof_count = (~is_real).sum()
        fpr = (~is_real & predicted_real).sum() / max(spoof_count, 1)

        tpr_list.append(tpr)
        fpr_list.append(fpr)

    # Sort by FPR for AUC calculation
    pairs = sorted(zip(fpr_list, tpr_list))
    fpr_sorted = [p[0] for p in pairs]
    tpr_sorted = [p[1] for p in pairs]

    auc = np.trapz(tpr_sorted, fpr_sorted)
    return auc


def main():
    parser = argparse.ArgumentParser(description="Evaluate anti-spoof model")
    parser.add_argument("--model", type=str, choices=list(MODEL_MAP.keys()))
    parser.add_argument("--weights", type=str, help="PyTorch weights path")
    parser.add_argument("--model2", type=str, choices=list(MODEL_MAP.keys()),
                        help="Second model for ensemble evaluation")
    parser.add_argument("--weights2", type=str,
                        help="Second model weights path")
    parser.add_argument("--onnx", type=str, help="ONNX model path")
    parser.add_argument("--data-dir", type=str, required=True,
                        help="Validation data directory")
    parser.add_argument("--data-dir2", type=str,
                        help="Validation data for model 2 (if different scale)")
    parser.add_argument("--input-size", type=int, default=80)
    parser.add_argument("--num-classes", type=int, default=3)
    args = parser.parse_args()

    # Load model(s)
    if args.onnx:
        import onnxruntime as ort
        session = ort.InferenceSession(
            args.onnx, providers=["CPUExecutionProvider"]
        )
        predict_fn = lambda path: predict_onnx(session, path, args.input_size)
        model_desc = f"ONNX: {args.onnx}"
    elif args.model and args.weights:
        model = load_model(args.model, args.weights, args.input_size,
                           args.num_classes)
        predict_fn = lambda path: predict_pytorch(model, path, args.input_size)
        model_desc = f"PyTorch: {args.model} ({args.weights})"
    else:
        parser.error("Provide --model/--weights or --onnx")
        return

    samples = get_samples(args.data_dir)
    print(f"Model: {model_desc}")
    print(f"Evaluating {len(samples)} samples from {args.data_dir}")
    print()

    # Run predictions
    labels = []
    real_scores = []
    correct = 0
    total = 0
    class_stats = {}

    for path, label in samples:
        probs = predict_fn(path)
        if probs is None:
            continue

        # For ensemble: add second model's predictions
        if args.model2 and args.weights2:
            model2 = load_model(args.model2, args.weights2, args.input_size,
                                args.num_classes)
            data_dir2 = args.data_dir2 or args.data_dir
            # Find corresponding image in model2's data dir
            rel_path = os.path.relpath(path, args.data_dir)
            path2 = os.path.join(data_dir2, rel_path)
            if os.path.exists(path2):
                probs2 = predict_pytorch(model2, path2, args.input_size)
                if probs2 is not None:
                    probs = (probs + probs2) / 2

        predicted = int(np.argmax(probs))
        real_score = float(probs[0])  # Class 0 = real

        labels.append(label)
        real_scores.append(real_score)

        is_correct = predicted == label
        if label == 0:
            is_correct = predicted == 0  # Real
        else:
            is_correct = predicted != 0  # Any spoof class

        if is_correct:
            correct += 1
        total += 1

        cls_name = {0: "Real", 1: "Spoof-Print", 2: "Spoof-Replay"}.get(
            label, f"Class-{label}"
        )
        if cls_name not in class_stats:
            class_stats[cls_name] = {"correct": 0, "total": 0}
        class_stats[cls_name]["total"] += 1
        if is_correct:
            class_stats[cls_name]["correct"] += 1

    # Compute metrics
    accuracy = 100.0 * correct / total if total > 0 else 0
    apcer, bpcer, acer = compute_metrics(labels, real_scores, threshold=0.5)
    auc = compute_auc(labels, real_scores)

    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Overall Accuracy:  {accuracy:.2f}% ({correct}/{total})")
    print(f"AUC:               {auc:.4f}")
    print(f"APCER (spoof→real): {apcer:.4f} ({apcer * 100:.2f}%)")
    print(f"BPCER (real→spoof): {bpcer:.4f} ({bpcer * 100:.2f}%)")
    print(f"ACER (average):     {acer:.4f} ({acer * 100:.2f}%)")
    print()
    print("Per-class accuracy:")
    for cls_name in sorted(class_stats.keys()):
        s = class_stats[cls_name]
        cls_acc = 100.0 * s["correct"] / s["total"] if s["total"] > 0 else 0
        print(f"  {cls_name}: {cls_acc:.2f}% ({s['correct']}/{s['total']})")
    print()

    # Find optimal threshold
    best_acer = 1.0
    best_threshold = 0.5
    for t in np.linspace(0.1, 0.9, 81):
        a, b, c = compute_metrics(labels, real_scores, threshold=t)
        if c < best_acer:
            best_acer = c
            best_threshold = t

    print(f"Optimal threshold:  {best_threshold:.3f} (ACER={best_acer:.4f})")
    print()
    print("To use this threshold in production, set:")
    print(f"  ANTISPOOF_REAL_SCORE_MIN={best_threshold:.2f}")


if __name__ == "__main__":
    main()
