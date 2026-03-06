"""Dataset loader for face anti-spoofing training.

Supports the standard ImageFolder structure:
    dataset_dir/
        0/  (real faces)
        1/  (spoof type 1 - print attacks)
        2/  (spoof type 2 - replay attacks)

Generates Fourier Transform targets on-the-fly for auxiliary supervision.
"""

import os

import cv2
import numpy as np
import torch
from torch.utils.data import Dataset
from torchvision import transforms


class DatasetFolderFT(Dataset):
    """Anti-spoofing dataset with Fourier Transform auxiliary targets.

    Args:
        root:      Path to dataset root (contains class subdirs 0/, 1/, 2/)
        transform: Torchvision transforms for the image
        ft_width:  Width of FT target map (default: 10)
        ft_height: Height of FT target map (default: 10)
    """

    def __init__(self, root, transform=None, ft_width=10, ft_height=10):
        self.root = root
        self.transform = transform or transforms.Compose([transforms.ToTensor()])
        self.ft_width = ft_width
        self.ft_height = ft_height

        self.samples = []
        self.class_to_idx = {}

        # Walk class directories
        for class_name in sorted(os.listdir(root)):
            class_dir = os.path.join(root, class_name)
            if not os.path.isdir(class_dir):
                continue
            try:
                class_idx = int(class_name)
            except ValueError:
                continue

            self.class_to_idx[class_name] = class_idx

            for fname in sorted(os.listdir(class_dir)):
                fpath = os.path.join(class_dir, fname)
                if self._is_image(fname):
                    self.samples.append((fpath, class_idx))

        print(
            f"[DatasetFolderFT] Loaded {len(self.samples)} samples "
            f"from {root} ({len(self.class_to_idx)} classes)"
        )

    @staticmethod
    def _is_image(filename):
        ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
        return ext in {"jpg", "jpeg", "png", "bmp", "webp", "tif", "tiff"}

    def _generate_ft_target(self, image):
        """Generate Fourier Transform magnitude spectrum as training target.

        Real faces have rich high-frequency content from skin texture.
        Spoofs lose high-frequency detail from recapture degradation.
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        resized = cv2.resize(gray, (self.ft_width * 8, self.ft_height * 8))

        f = np.fft.fft2(resized.astype(np.float32))
        fshift = np.fft.fftshift(f)
        magnitude = np.log1p(np.abs(fshift))

        # Normalize to [0, 1]
        if magnitude.max() > magnitude.min():
            magnitude = (magnitude - magnitude.min()) / (
                magnitude.max() - magnitude.min()
            )

        # Resize to target FT map dimensions
        ft_target = cv2.resize(magnitude, (self.ft_width, self.ft_height))
        return ft_target.astype(np.float32)

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        path, label = self.samples[idx]

        # Load image
        image = cv2.imread(path)
        if image is None:
            raise RuntimeError(f"Failed to load image: {path}")

        # Generate FT target
        ft_target = self._generate_ft_target(image)
        ft_target = torch.from_numpy(ft_target).unsqueeze(0)  # (1, H, W)

        # Apply transforms to image
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        if self.transform:
            image_tensor = self.transform(image_rgb)
        else:
            image_tensor = transforms.ToTensor()(image_rgb)

        return image_tensor, ft_target, label
