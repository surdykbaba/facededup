#!/usr/bin/env python3
"""Train Silent-Face anti-spoof model.

Trains a MiniFASNet variant (V2 or V1SE) with Fourier Transform auxiliary
supervision. Each model is trained at a specific scale (2.7 or 4.0).

Usage:
    # Train MiniFASNetV2 on scale 2.7 crops
    python train.py --model V2 --patch-info 2.7_80x80

    # Train MiniFASNetV1SE on scale 4.0 crops
    python train.py --model V1SE --patch-info 4.0_80x80

    # Fine-tune from pre-trained weights
    python train.py --model V2 --patch-info 2.7_80x80 \
        --resume ./pretrained/MiniFASNetV2.pth

    # Custom hyperparameters
    python train.py --model V2 --patch-info 2.7_80x80 \
        --lr 0.01 --epochs 30 --batch-size 256
"""

import argparse
import logging
import os
import time

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from torch.utils.tensorboard import SummaryWriter
from torchvision import transforms

from src.data_io.dataset_folder import DatasetFolderFT
from src.model_lib.MiniFASNet import (
    MiniFASNetV1,
    MiniFASNetV1SE,
    MiniFASNetV2,
    MiniFASNetV2SE,
    get_kernel,
)
from src.model_lib.MultiFTNet import MultiFTNet

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

MODEL_MAP = {
    # (model_fn, ft_channels) — ft_channels must match conv_5 output channels
    # "1.8M" config: conv_5 = [[192,96,192]] → output 192
    # "1.8M_" config: conv_5 = [[128,64,128]] → output 128
    "V1": (MiniFASNetV1, 192),
    "V2": (MiniFASNetV2, 128),
    "V1SE": (MiniFASNetV1SE, 192),
    "V2SE": (MiniFASNetV2SE, 128),
}


def get_transforms(input_size=80, augment=True):
    """Get train/val transforms."""
    if augment:
        return transforms.Compose([
            transforms.ToPILImage(),
            transforms.RandomHorizontalFlip(p=0.5),
            transforms.ColorJitter(
                brightness=0.3, contrast=0.3, saturation=0.2, hue=0.1,
            ),
            transforms.RandomRotation(15),
            transforms.Resize((input_size, input_size)),
            transforms.ToTensor(),
        ])
    else:
        return transforms.Compose([
            transforms.ToPILImage(),
            transforms.Resize((input_size, input_size)),
            transforms.ToTensor(),
        ])


def load_pretrained(model, path, device):
    """Load pre-trained weights, handling DataParallel 'module.' prefix."""
    state_dict = torch.load(path, map_location=device, weights_only=True)

    # Remove 'module.' prefix if saved from DataParallel
    from collections import OrderedDict
    new_state_dict = OrderedDict()
    for k, v in state_dict.items():
        name = k.replace("module.", "")
        new_state_dict[name] = v

    # Try loading into backbone (if MultiFTNet wrapper)
    try:
        model.backbone.load_state_dict(new_state_dict, strict=False)
        logger.info("Loaded pre-trained weights into backbone from %s", path)
    except (AttributeError, RuntimeError):
        model.load_state_dict(new_state_dict, strict=False)
        logger.info("Loaded pre-trained weights from %s", path)


def train_one_epoch(model, loader, criterion_cls, criterion_ft, optimizer,
                    device, epoch, writer, log_freq=10):
    """Train for one epoch."""
    model.train()
    running_loss = 0.0
    running_cls_loss = 0.0
    running_ft_loss = 0.0
    correct = 0
    total = 0

    for i, (images, ft_targets, labels) in enumerate(loader):
        images = images.to(device)
        ft_targets = ft_targets.to(device)
        labels = labels.to(device)

        optimizer.zero_grad()

        cls_out, ft_out = model(images)

        # Resize FT output to match target size
        if ft_out.shape[-2:] != ft_targets.shape[-2:]:
            ft_out = nn.functional.interpolate(
                ft_out, size=ft_targets.shape[-2:], mode="bilinear",
                align_corners=False,
            )

        loss_cls = criterion_cls(cls_out, labels)
        loss_ft = criterion_ft(ft_out, ft_targets)
        loss = 0.5 * loss_cls + 0.5 * loss_ft

        loss.backward()
        optimizer.step()

        running_loss += loss.item()
        running_cls_loss += loss_cls.item()
        running_ft_loss += loss_ft.item()

        _, predicted = cls_out.max(1)
        total += labels.size(0)
        correct += predicted.eq(labels).sum().item()

        if (i + 1) % log_freq == 0:
            step = epoch * len(loader) + i
            writer.add_scalar("train/loss", loss.item(), step)
            writer.add_scalar("train/loss_cls", loss_cls.item(), step)
            writer.add_scalar("train/loss_ft", loss_ft.item(), step)
            writer.add_scalar("train/accuracy", correct / total, step)

            logger.info(
                "Epoch %d [%d/%d] loss=%.4f (cls=%.4f ft=%.4f) acc=%.2f%%",
                epoch, i + 1, len(loader), loss.item(),
                loss_cls.item(), loss_ft.item(), 100.0 * correct / total,
            )

    avg_loss = running_loss / len(loader)
    accuracy = 100.0 * correct / total
    return avg_loss, accuracy


@torch.no_grad()
def validate(model, loader, criterion_cls, device):
    """Validate the model."""
    model.eval()
    running_loss = 0.0
    correct = 0
    total = 0

    # Track per-class accuracy
    class_correct = {}
    class_total = {}

    for images, _, labels in loader:
        images = images.to(device)
        labels = labels.to(device)

        cls_out = model(images)
        loss = criterion_cls(cls_out, labels)

        running_loss += loss.item()
        _, predicted = cls_out.max(1)
        total += labels.size(0)
        correct += predicted.eq(labels).sum().item()

        for label, pred in zip(labels, predicted):
            lbl = label.item()
            class_total[lbl] = class_total.get(lbl, 0) + 1
            if pred.item() == lbl:
                class_correct[lbl] = class_correct.get(lbl, 0) + 1

    avg_loss = running_loss / len(loader) if len(loader) > 0 else 0
    accuracy = 100.0 * correct / total if total > 0 else 0

    # Log per-class accuracy
    for cls in sorted(class_total.keys()):
        cls_acc = 100.0 * class_correct.get(cls, 0) / class_total[cls]
        cls_name = {0: "Real", 1: "Spoof-Print", 2: "Spoof-Replay"}.get(
            cls, f"Class-{cls}"
        )
        logger.info("  %s: %.2f%% (%d/%d)", cls_name, cls_acc,
                     class_correct.get(cls, 0), class_total[cls])

    return avg_loss, accuracy


def main():
    parser = argparse.ArgumentParser(description="Train anti-spoof model")
    parser.add_argument(
        "--model", type=str, default="V2", choices=list(MODEL_MAP.keys()),
        help="Model variant (default: V2)",
    )
    parser.add_argument(
        "--patch-info", type=str, required=True,
        help="Patch subdir name (e.g., 2.7_80x80)",
    )
    parser.add_argument(
        "--data-dir", type=str, default="./datasets",
        help="Root dataset directory (default: ./datasets)",
    )
    parser.add_argument(
        "--resume", type=str, default=None,
        help="Path to pre-trained .pth weights for fine-tuning",
    )
    parser.add_argument("--lr", type=float, default=0.01,
                        help="Learning rate (default: 0.01)")
    parser.add_argument("--epochs", type=int, default=25,
                        help="Number of epochs (default: 25)")
    parser.add_argument("--batch-size", type=int, default=256,
                        help="Batch size (default: 256)")
    parser.add_argument("--num-workers", type=int, default=4,
                        help="DataLoader workers (default: 4)")
    parser.add_argument("--lr-milestones", nargs="+", type=int,
                        default=[10, 15, 22],
                        help="LR decay milestones (default: 10 15 22)")
    parser.add_argument("--lr-gamma", type=float, default=0.1,
                        help="LR decay factor (default: 0.1)")
    parser.add_argument("--weight-decay", type=float, default=5e-4,
                        help="Weight decay (default: 5e-4)")
    parser.add_argument("--save-dir", type=str, default="./checkpoints",
                        help="Checkpoint save directory (default: ./checkpoints)")
    parser.add_argument("--log-dir", type=str, default="./logs",
                        help="TensorBoard log directory (default: ./logs)")
    parser.add_argument("--input-size", type=int, default=80,
                        help="Input image size (default: 80)")
    parser.add_argument("--num-classes", type=int, default=3,
                        help="Number of classes (default: 3)")
    parser.add_argument("--device", type=str, default=None,
                        help="Device (auto-detect if not specified)")
    args = parser.parse_args()

    # Device
    if args.device:
        device = torch.device(args.device)
    elif torch.cuda.is_available():
        device = torch.device("cuda")
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        device = torch.device("mps")
    else:
        device = torch.device("cpu")
    logger.info("Using device: %s", device)

    # Directories
    os.makedirs(args.save_dir, exist_ok=True)
    os.makedirs(args.log_dir, exist_ok=True)

    train_dir = os.path.join(args.data_dir, args.patch_info, "train")
    val_dir = os.path.join(args.data_dir, args.patch_info, "val")

    if not os.path.exists(train_dir):
        logger.error("Training data not found: %s", train_dir)
        logger.error("Run prepare_dataset.py first to generate training data.")
        return

    # Datasets
    train_transform = get_transforms(args.input_size, augment=True)
    val_transform = get_transforms(args.input_size, augment=False)

    train_dataset = DatasetFolderFT(train_dir, transform=train_transform)
    val_dataset = DatasetFolderFT(val_dir, transform=val_transform)

    train_loader = DataLoader(
        train_dataset, batch_size=args.batch_size, shuffle=True,
        num_workers=args.num_workers, pin_memory=True, drop_last=True,
    )
    val_loader = DataLoader(
        val_dataset, batch_size=args.batch_size, shuffle=False,
        num_workers=args.num_workers, pin_memory=True,
    )

    logger.info("Train: %d samples, Val: %d samples",
                len(train_dataset), len(val_dataset))

    # Model
    kernel = get_kernel(args.input_size, args.input_size)
    model_fn, ft_channels = MODEL_MAP[args.model]
    backbone = model_fn(
        conv6_kernel=kernel, num_classes=args.num_classes,
    )
    model = MultiFTNet(backbone, ft_channels=ft_channels)

    if args.resume:
        load_pretrained(model, args.resume, device)

    model = model.to(device)

    # Use DataParallel if multiple GPUs
    if torch.cuda.device_count() > 1:
        logger.info("Using %d GPUs", torch.cuda.device_count())
        model = nn.DataParallel(model)

    # Loss, optimizer, scheduler
    criterion_cls = nn.CrossEntropyLoss()
    criterion_ft = nn.MSELoss()
    optimizer = optim.SGD(
        model.parameters(), lr=args.lr, momentum=0.9,
        weight_decay=args.weight_decay,
    )
    scheduler = optim.lr_scheduler.MultiStepLR(
        optimizer, milestones=args.lr_milestones, gamma=args.lr_gamma,
    )

    # TensorBoard
    run_name = f"{args.model}_{args.patch_info}_{time.strftime('%Y%m%d_%H%M%S')}"
    writer = SummaryWriter(os.path.join(args.log_dir, run_name))

    # Training loop
    best_val_acc = 0.0
    logger.info("Starting training: %s on %s", args.model, args.patch_info)
    logger.info("Epochs: %d, LR: %s, Batch: %d", args.epochs, args.lr,
                args.batch_size)

    for epoch in range(args.epochs):
        lr = optimizer.param_groups[0]["lr"]
        logger.info("=== Epoch %d/%d (lr=%.6f) ===", epoch + 1, args.epochs, lr)

        train_loss, train_acc = train_one_epoch(
            model, train_loader, criterion_cls, criterion_ft,
            optimizer, device, epoch, writer,
        )
        val_loss, val_acc = validate(model, val_loader, criterion_cls, device)

        scheduler.step()

        writer.add_scalar("val/loss", val_loss, epoch)
        writer.add_scalar("val/accuracy", val_acc, epoch)
        writer.add_scalar("lr", lr, epoch)

        logger.info(
            "Epoch %d: train_loss=%.4f train_acc=%.2f%% "
            "val_loss=%.4f val_acc=%.2f%%",
            epoch + 1, train_loss, train_acc, val_loss, val_acc,
        )

        # Save checkpoint
        ckpt_path = os.path.join(
            args.save_dir,
            f"{args.model}_{args.patch_info}_epoch{epoch + 1}.pth",
        )
        state = model.module.state_dict() if hasattr(model, "module") \
            else model.state_dict()
        torch.save(state, ckpt_path)

        # Save best
        if val_acc > best_val_acc:
            best_val_acc = val_acc
            best_path = os.path.join(
                args.save_dir,
                f"{args.model}_{args.patch_info}_best.pth",
            )
            torch.save(state, best_path)
            logger.info("New best model: %.2f%% → %s", val_acc, best_path)

    writer.close()
    logger.info("Training complete. Best val accuracy: %.2f%%", best_val_acc)
    logger.info("Best model saved to: %s",
                os.path.join(args.save_dir,
                             f"{args.model}_{args.patch_info}_best.pth"))


if __name__ == "__main__":
    main()
