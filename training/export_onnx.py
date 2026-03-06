#!/usr/bin/env python3
"""Export trained PyTorch anti-spoof model to ONNX format.

Exports the classification backbone (without FT branch) to ONNX,
ready to drop into the FaceDedup API's AntiSpoofService.

Usage:
    # Export MiniFASNetV2 (scale 2.7)
    python export_onnx.py \
        --model V2 \
        --weights ./checkpoints/V2_2.7_80x80_best.pth \
        --output ../app/models/anti_spoof/MiniFASNetV2.onnx

    # Export MiniFASNetV1SE (scale 4.0)
    python export_onnx.py \
        --model V1SE \
        --weights ./checkpoints/V1SE_4.0_80x80_best.pth \
        --output ../app/models/anti_spoof/MiniFASNetV1SE.onnx

    # Verify ONNX model matches PyTorch output
    python export_onnx.py \
        --model V2 \
        --weights ./checkpoints/V2_2.7_80x80_best.pth \
        --output ./MiniFASNetV2.onnx \
        --verify
"""

import argparse
import os
from collections import OrderedDict

import numpy as np
import torch

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


def load_weights(model, weights_path):
    """Load weights, handling DataParallel prefix and MultiFTNet wrapper."""
    state_dict = torch.load(weights_path, map_location="cpu", weights_only=True)

    # Remove 'module.' prefix (DataParallel)
    cleaned = OrderedDict()
    for k, v in state_dict.items():
        name = k.replace("module.", "")
        # Remove 'backbone.' prefix (MultiFTNet)
        name = name.replace("backbone.", "")
        cleaned[name] = v

    # Filter out FT generator keys
    model_keys = set(model.state_dict().keys())
    filtered = OrderedDict(
        (k, v) for k, v in cleaned.items() if k in model_keys
    )

    missing = model_keys - set(filtered.keys())
    if missing:
        print(f"WARNING: Missing keys: {missing}")

    model.load_state_dict(filtered, strict=False)
    print(f"Loaded weights from {weights_path} ({len(filtered)} params)")


def export(model, output_path, input_size=80, opset_version=11):
    """Export PyTorch model to ONNX."""
    model.eval()

    dummy_input = torch.randn(1, 3, input_size, input_size)

    torch.onnx.export(
        model,
        dummy_input,
        output_path,
        export_params=True,
        opset_version=opset_version,
        do_constant_folding=True,
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={
            "input": {0: "batch_size"},
            "output": {0: "batch_size"},
        },
    )

    file_size = os.path.getsize(output_path) / (1024 * 1024)
    print(f"Exported ONNX model: {output_path} ({file_size:.2f} MB)")


def verify_onnx(model, onnx_path, input_size=80):
    """Verify ONNX model output matches PyTorch."""
    import onnxruntime as ort

    model.eval()

    # Random test input
    test_input = torch.randn(1, 3, input_size, input_size)

    # PyTorch inference
    with torch.no_grad():
        pt_output = model(test_input).numpy()

    # ONNX Runtime inference
    session = ort.InferenceSession(
        onnx_path, providers=["CPUExecutionProvider"]
    )
    ort_output = session.run(None, {"input": test_input.numpy()})[0]

    # Compare
    max_diff = np.max(np.abs(pt_output - ort_output))
    mean_diff = np.mean(np.abs(pt_output - ort_output))

    print(f"\nVerification Results:")
    print(f"  PyTorch output:  {pt_output[0]}")
    print(f"  ONNX output:     {ort_output[0]}")
    print(f"  Max difference:  {max_diff:.8f}")
    print(f"  Mean difference: {mean_diff:.8f}")

    if max_diff < 1e-4:
        print("  ✓ ONNX model matches PyTorch output")
    else:
        print("  ✗ WARNING: Outputs differ significantly!")


def main():
    parser = argparse.ArgumentParser(
        description="Export anti-spoof model to ONNX"
    )
    parser.add_argument(
        "--model", type=str, required=True, choices=list(MODEL_MAP.keys()),
        help="Model variant",
    )
    parser.add_argument(
        "--weights", type=str, required=True,
        help="Path to trained .pth weights",
    )
    parser.add_argument(
        "--output", type=str, required=True,
        help="Output ONNX file path",
    )
    parser.add_argument(
        "--input-size", type=int, default=80,
        help="Input image size (default: 80)",
    )
    parser.add_argument(
        "--num-classes", type=int, default=3,
        help="Number of classes (default: 3)",
    )
    parser.add_argument(
        "--opset", type=int, default=11,
        help="ONNX opset version (default: 11)",
    )
    parser.add_argument(
        "--verify", action="store_true",
        help="Verify ONNX output matches PyTorch",
    )
    args = parser.parse_args()

    kernel = get_kernel(args.input_size, args.input_size)
    model_fn = MODEL_MAP[args.model]
    model = model_fn(conv6_kernel=kernel, num_classes=args.num_classes)

    load_weights(model, args.weights)

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    export(model, args.output, args.input_size, args.opset)

    if args.verify:
        verify_onnx(model, args.output, args.input_size)

    print(f"\nTo deploy, copy {args.output} to app/models/anti_spoof/")


if __name__ == "__main__":
    main()
