# Anti-Spoof Model Training

Train your own Silent-Face anti-spoof models for the FaceDedup API.

## Architecture

Two separate models work as an ensemble:

| Model | Scale | What it sees |
|-------|-------|-------------|
| **MiniFASNetV2** | 2.7 | Face + surrounding context |
| **MiniFASNetV1SE** | 4.0 | Tight face crop with SE attention |

Both models output 3 classes: `0 = Real`, `1 = Print Attack`, `2 = Replay Attack`.
Predictions are fused by averaging softmax probabilities.

## Quick Start

### 1. Install dependencies

```bash
cd training
pip install -r requirements.txt
```

### 2. Organize your data

```
raw_data/
  0/    # Real live selfies (from phone cameras)
  1/    # Print attacks (photos of photos)
  2/    # Replay attacks (photos of screens)
```

Put at least 500+ images per class for reasonable results. More is better.

**Public datasets you can use:**
- [CelebA-Spoof](https://github.com/ZhangYuanhan-AI/CelebA-Spoof) — 625K images (best)
- [CASIA-FASD](http://www.cbsr.ia.ac.cn/english/FASDB.asp) — print + replay
- [OULU-NPU](https://sites.google.com/site/aboralisgroup/datasets) — phone-captured
- Collect your own real selfies + spoof attempts

### 3. Prepare training data

```bash
python prepare_dataset.py \
    --input-dir ./raw_data \
    --output-dir ./datasets \
    --scales 2.7 4.0 \
    --val-split 0.15
```

This will:
- Detect faces using InsightFace
- Crop faces at scale 2.7 and 4.0
- Resize to 80x80
- Split into train/val (85%/15%)

### 4. Train models

```bash
# Train MiniFASNetV2 on scale 2.7 crops
python train.py --model V2 --patch-info 2.7_80x80 --epochs 25 --batch-size 256

# Train MiniFASNetV1SE on scale 4.0 crops
python train.py --model V1SE --patch-info 4.0_80x80 --epochs 25 --batch-size 256
```

**Fine-tune from pre-trained weights** (recommended for faster convergence):
```bash
python train.py --model V2 --patch-info 2.7_80x80 \
    --resume ../app/models/anti_spoof/MiniFASNetV2.pth \
    --lr 0.001 --epochs 15

python train.py --model V1SE --patch-info 4.0_80x80 \
    --resume ../app/models/anti_spoof/MiniFASNetV1SE.pth \
    --lr 0.001 --epochs 15
```

Monitor training with TensorBoard:
```bash
tensorboard --logdir ./logs
```

### 5. Evaluate

```bash
python evaluate.py \
    --model V2 \
    --weights ./checkpoints/V2_2.7_80x80_best.pth \
    --data-dir ./datasets/2.7_80x80/val
```

This outputs APCER, BPCER, ACER, AUC and the optimal threshold.

### 6. Export to ONNX

```bash
# Export both models
python export_onnx.py \
    --model V2 \
    --weights ./checkpoints/V2_2.7_80x80_best.pth \
    --output ../app/models/anti_spoof/MiniFASNetV2.onnx \
    --verify

python export_onnx.py \
    --model V1SE \
    --weights ./checkpoints/V1SE_4.0_80x80_best.pth \
    --output ../app/models/anti_spoof/MiniFASNetV1SE.onnx \
    --verify
```

### 7. Deploy

The exported ONNX files replace the existing ones in `app/models/anti_spoof/`.
Rebuild and deploy:

```bash
docker compose build && docker compose up -d
```

Update `ANTISPOOF_REAL_SCORE_MIN` in your `.env` based on the evaluation output.

## Training Tips

- **Start with fine-tuning** — Use the pre-trained weights and a lower learning rate (0.001). This converges faster.
- **Collect your own data** — Photos from your actual users' phone cameras are the most valuable training data.
- **Balance classes** — Keep roughly equal numbers per class.
- **Watch BPCER** — This is the "real faces rejected" rate. You want this below 5%.
- **Use the evaluate script** to find the right `ANTISPOOF_REAL_SCORE_MIN` threshold before deploying.

## Key Metrics

| Metric | What it means | Target |
|--------|--------------|--------|
| **APCER** | Spoof images classified as real | < 10% |
| **BPCER** | Real images classified as spoof | < 5% |
| **ACER** | Average of APCER and BPCER | < 7% |
| **AUC** | Area Under ROC Curve | > 0.95 |

## Files

```
training/
  prepare_dataset.py   — Generate multi-scale face crops from raw images
  train.py             — Train MiniFASNet models with FT supervision
  evaluate.py          — Compute APCER/BPCER/ACER/AUC metrics
  export_onnx.py       — Export trained models to ONNX for production
  requirements.txt     — Training dependencies (torch, torchvision, etc.)
  src/
    model_lib/
      MiniFASNet.py    — Model architectures (V1, V2, V1SE, V2SE)
      MultiFTNet.py    — Multi-task training wrapper with FT branch
    data_io/
      dataset_folder.py — Dataset loader with FT target generation
```
