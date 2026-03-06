"""Multi-task Fourier Transform Network for face anti-spoofing.

Wraps a MiniFASNet backbone and adds a Fourier Transform auxiliary branch.
During training, it outputs both classification logits and FT feature maps.
During inference, only classification logits are returned.

Reference: https://github.com/minivision-ai/Silent-Face-Anti-Spoofing
"""

import torch.nn as nn


class FTGenerator(nn.Module):
    """Generates Fourier Transform feature maps from intermediate features.

    Input:  feature maps from backbone (after conv_5)
    Output: single-channel FT map (ft_height x ft_width)
    """

    def __init__(self, in_channels=48, out_channels=1):
        super().__init__()
        self.ft = nn.Sequential(
            nn.Conv2d(in_channels, 128, kernel_size=3, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(inplace=True),
            nn.Conv2d(128, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.Conv2d(64, out_channels, kernel_size=3, padding=1),
        )

    def forward(self, x):
        return self.ft(x)


class MultiFTNet(nn.Module):
    """Multi-task network: classification + Fourier spectrum supervision.

    During training:
      - Returns (classification_logits, ft_map)
      - Train with: loss = 0.5 * CE(logits, label) + 0.5 * MSE(ft_map, target_ft)

    During inference:
      - Returns classification_logits only
    """

    def __init__(self, backbone, ft_channels=None):
        super().__init__()
        self.backbone = backbone

        # Determine FT input channels from backbone's conv_5 output
        if ft_channels is None:
            # Default: last block output channels
            ft_channels = 48  # for 1.8M variants

        self.ft_generator = FTGenerator(in_channels=ft_channels)

    def forward(self, x):
        # Extract intermediate features for FT branch
        out = self.backbone.conv1(x)
        out = self.backbone.conv2_dw(out)
        out = self.backbone.conv_23(out)
        out = self.backbone.conv_3(out)
        out = self.backbone.conv_34(out)
        out = self.backbone.conv_4(out)
        out = self.backbone.conv_45(out)
        out = self.backbone.conv_5(out)

        # FT branch (from intermediate features)
        ft_map = self.ft_generator(out)

        # Classification branch (continue backbone)
        out = self.backbone.conv_6_sep(out)
        out = self.backbone.conv_6_dw(out)
        out = self.backbone.conv_6_flatten(out)
        out = self.backbone.linear(out)
        out = self.backbone.bn(out)
        out = self.backbone.drop(out)
        cls_out = self.backbone.prob(out)

        if self.training:
            return cls_out, ft_map
        return cls_out
