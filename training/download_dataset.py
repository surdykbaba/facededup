#!/usr/bin/env python3
"""Download and organize face anti-spoofing dataset from Hugging Face.

Uses streaming mode for fast downloads. Tries multiple datasets.
Organizes into:
    raw_data/0/ (real faces)
    raw_data/1/ (spoof faces - print and replay combined)
"""

import os
import sys
import time


def download_dataset(max_per_class=2000):
    """Download face anti-spoofing images from HuggingFace."""
    from datasets import load_dataset
    from PIL import Image

    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw_data")
    os.makedirs(os.path.join(output_dir, "0"), exist_ok=True)
    os.makedirs(os.path.join(output_dir, "1"), exist_ok=True)
    os.makedirs(os.path.join(output_dir, "2"), exist_ok=True)

    counts = {0: 0, 1: 0, 2: 0}
    start_time = time.time()

    # Dataset 1: nguyenkhoa CelebA spoof test set (parquet, fast)
    print("=" * 60)
    print("Downloading nguyenkhoa/celeba-spoof-for-face-antispoofing-test")
    print("=" * 60)
    try:
        ds = load_dataset(
            "nguyenkhoa/celeba-spoof-for-face-antispoofing-test",
            streaming=True
        )
        for split_name in ds.keys():
            print(f"  Processing split: {split_name}")
            for i, sample in enumerate(ds[split_name]):
                if all(c >= max_per_class for c in counts.values()):
                    break

                image = sample.get("cropped_image") or sample.get("image")
                if image is None:
                    continue

                raw_label = sample.get("labels", sample.get("label", 0))
                label_name = str(sample.get("labelNames", "")).lower()

                # Map: live/real = 0, spoof = 1
                if label_name in ("live", "real", "genuine"):
                    label = 0
                elif label_name in ("spoof", "fake", "attack"):
                    label = 1
                elif isinstance(raw_label, (int, float)):
                    label = 0 if int(raw_label) == 0 else 1
                else:
                    label = 1

                if counts[label] >= max_per_class:
                    continue

                if not isinstance(image, Image.Image):
                    continue

                fname = f"celeba_{split_name}_{i:06d}.png"
                out_path = os.path.join(output_dir, str(label), fname)
                try:
                    if image.mode != "RGB":
                        image = image.convert("RGB")
                    image.save(out_path)
                    counts[label] += 1
                except Exception:
                    continue

                total = sum(counts.values())
                if total % 200 == 0:
                    elapsed = time.time() - start_time
                    rate = total / elapsed if elapsed > 0 else 0
                    print(f"    Saved {total} images ({rate:.1f}/sec) - "
                          f"Real: {counts[0]}, Spoof: {counts[1]}")

    except Exception as e:
        print(f"  Failed: {e}")

    # Dataset 2: Ar4ikov CelebA Spoof (parquet, larger)
    if not all(c >= max_per_class for c in counts.values()):
        print("\n" + "=" * 60)
        print("Downloading Ar4ikov/celebA_spoof")
        print("=" * 60)
        try:
            ds2 = load_dataset("Ar4ikov/celebA_spoof", streaming=True)
            for split_name in ds2.keys():
                print(f"  Processing split: {split_name}")
                for i, sample in enumerate(ds2[split_name]):
                    if all(c >= max_per_class for c in counts.values()):
                        break

                    image = sample.get("image") or sample.get("cropped_image")
                    if image is None:
                        continue

                    raw_label = sample.get("label", sample.get("labels", 0))
                    label_name = str(sample.get("labelNames",
                                     sample.get("label_name", ""))).lower()

                    if label_name in ("live", "real", "genuine"):
                        label = 0
                    elif label_name in ("spoof", "fake", "attack"):
                        label = 1
                    elif isinstance(raw_label, (int, float)):
                        label = 0 if int(raw_label) == 0 else 1
                    else:
                        label = 1

                    if counts[label] >= max_per_class:
                        continue

                    if not isinstance(image, Image.Image):
                        continue

                    fname = f"celeba2_{split_name}_{i:06d}.png"
                    out_path = os.path.join(output_dir, str(label), fname)
                    try:
                        if image.mode != "RGB":
                            image = image.convert("RGB")
                        image.save(out_path)
                        counts[label] += 1
                    except Exception:
                        continue

                    total = sum(counts.values())
                    if total % 200 == 0:
                        elapsed = time.time() - start_time
                        rate = total / elapsed if elapsed > 0 else 0
                        print(f"    Saved {total} images ({rate:.1f}/sec) - "
                              f"Real: {counts[0]}, Spoof: {counts[1]}")

        except Exception as e:
            print(f"  Failed: {e}")

    total = sum(counts.values())
    elapsed = time.time() - start_time
    print(f"\n{'=' * 60}")
    print(f"DOWNLOAD COMPLETE in {elapsed:.0f}s")
    print(f"{'=' * 60}")
    print(f"Total images: {total}")
    print(f"  Class 0 (Real):   {counts[0]}")
    print(f"  Class 1 (Spoof):  {counts[1]}")
    print(f"  Class 2 (Replay): {counts[2]}")

    if total < 100:
        print("\nWARNING: Too few images downloaded.")
        print("Please manually download a dataset and organize into raw_data/0/ and raw_data/1/")
        sys.exit(1)
    elif counts[0] < 50 or counts[1] < 50:
        print("\nWARNING: Very imbalanced classes. Training may not work well.")

    return counts


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-per-class", type=int, default=2000,
                        help="Max images per class (default: 2000)")
    args = parser.parse_args()
    download_dataset(args.max_per_class)
