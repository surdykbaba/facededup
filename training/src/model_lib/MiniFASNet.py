"""MiniFASNet model architectures for face anti-spoofing.

Pruned MobileFaceNet-based architectures from Silent-Face-Anti-Spoofing.
Four variants: V1, V2, V1SE (with Squeeze-and-Excitation), V2SE.

Reference: https://github.com/minivision-ai/Silent-Face-Anti-Spoofing
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


# ---------------------------------------------------------------------------
# Channel configs (pruned MobileFaceNet variants)
# ---------------------------------------------------------------------------

keep_dict = {
    "1.8M": {
        "conv1": 48,
        "conv2_dw": 48,
        "conv_23": 48,
        "conv_3": [
            [48, 24, 48],
            [48, 24, 48],
            [48, 24, 48],
            [48, 24, 48],
        ],
        "conv_34": 96,
        "conv_4": [
            [96, 48, 96],
            [96, 48, 96],
            [96, 48, 96],
            [96, 48, 96],
            [96, 48, 96],
            [96, 48, 96],
        ],
        "conv_45": 192,
        "conv_5": [
            [192, 96, 192],
            [192, 96, 192],
        ],
        "conv_6_sep": 512,
    },
    "1.8M_": {
        "conv1": 48,
        "conv2_dw": 48,
        "conv_23": 48,
        "conv_3": [
            [48, 24, 48],
            [48, 24, 48],
            [48, 24, 48],
            [48, 24, 48],
        ],
        "conv_34": 96,
        "conv_4": [
            [96, 48, 96],
            [96, 48, 96],
            [96, 48, 96],
            [96, 48, 96],
            [96, 48, 96],
            [96, 48, 96],
        ],
        "conv_45": 128,
        "conv_5": [
            [128, 64, 128],
            [128, 64, 128],
        ],
        "conv_6_sep": 512,
    },
}


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------

class Conv_block(nn.Module):
    def __init__(self, in_c, out_c, kernel=(1, 1), stride=(1, 1),
                 padding=(0, 0), groups=1):
        super().__init__()
        self.conv = nn.Conv2d(in_c, out_c, kernel, stride, padding,
                              groups=groups, bias=False)
        self.bn = nn.BatchNorm2d(out_c)
        self.prelu = nn.PReLU(out_c)

    def forward(self, x):
        return self.prelu(self.bn(self.conv(x)))


class Linear_block(nn.Module):
    def __init__(self, in_c, out_c, kernel=(1, 1), stride=(1, 1),
                 padding=(0, 0), groups=1):
        super().__init__()
        self.conv = nn.Conv2d(in_c, out_c, kernel, stride, padding,
                              groups=groups, bias=False)
        self.bn = nn.BatchNorm2d(out_c)

    def forward(self, x):
        return self.bn(self.conv(x))


class Depth_Wise(nn.Module):
    def __init__(self, in_c, out_c, residual=False, kernel=(3, 3),
                 stride=(2, 2), padding=(1, 1), groups=1):
        super().__init__()
        self.conv = Conv_block(in_c, groups, kernel=(1, 1), padding=(0, 0),
                               stride=(1, 1))
        self.conv_dw = Conv_block(groups, groups, kernel=kernel,
                                  padding=padding, stride=stride,
                                  groups=groups)
        self.project = Linear_block(groups, out_c, kernel=(1, 1),
                                    padding=(0, 0), stride=(1, 1))
        self.residual = residual

    def forward(self, x):
        if self.residual:
            short_cut = x
        output = self.conv(x)
        output = self.conv_dw(output)
        output = self.project(output)
        if self.residual:
            output = output + short_cut
        return output


class Residual(nn.Module):
    def __init__(self, c, num_block, groups, kernel=(3, 3),
                 stride=(1, 1), padding=(1, 1)):
        super().__init__()
        modules = []
        for _ in range(num_block):
            modules.append(
                Depth_Wise(c[0], c[2], residual=True, kernel=kernel,
                           padding=padding, stride=stride, groups=c[1])
            )
        self.model = nn.Sequential(*modules)

    def forward(self, x):
        return self.model(x)


class SEModule(nn.Module):
    def __init__(self, channels, reduction=4):
        super().__init__()
        self.avg_pool = nn.AdaptiveAvgPool2d(1)
        self.fc1 = nn.Conv2d(channels, channels // reduction, kernel_size=1,
                             padding=0, bias=False)
        self.relu = nn.ReLU(inplace=True)
        self.fc2 = nn.Conv2d(channels // reduction, channels, kernel_size=1,
                             padding=0, bias=False)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        module_input = x
        x = self.avg_pool(x)
        x = self.fc1(x)
        x = self.relu(x)
        x = self.fc2(x)
        x = self.sigmoid(x)
        # Use torch.mul for ONNX compatibility
        return torch.mul(module_input, x)


class ResidualSE(nn.Module):
    def __init__(self, c, num_block, groups, kernel=(3, 3),
                 stride=(1, 1), padding=(1, 1)):
        super().__init__()
        modules = []
        for _ in range(num_block):
            modules.append(
                Depth_Wise(c[0], c[2], residual=True, kernel=kernel,
                           padding=padding, stride=stride, groups=c[1])
            )
        modules.append(SEModule(c[2]))
        self.model = nn.Sequential(*modules)

    def forward(self, x):
        return self.model(x)


class Flatten(nn.Module):
    def forward(self, x):
        return x.view(x.size(0), -1)


class L2Norm(nn.Module):
    def forward(self, x):
        return F.normalize(x)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def get_kernel(height, width):
    """Compute adaptive pooling kernel size from input dimensions."""
    return (height + 15) // 16, (width + 15) // 16


# ---------------------------------------------------------------------------
# MiniFASNet (base)
# ---------------------------------------------------------------------------

class MiniFASNet(nn.Module):
    def __init__(self, keep, embedding_size=128, conv6_kernel=(5, 5),
                 drop_p=0.2, num_classes=3, img_channel=3):
        super().__init__()
        self.conv1 = Conv_block(
            img_channel, keep["conv1"], kernel=(3, 3), stride=(2, 2),
            padding=(1, 1),
        )
        self.conv2_dw = Conv_block(
            keep["conv1"], keep["conv2_dw"], kernel=(3, 3), stride=(1, 1),
            padding=(1, 1), groups=keep["conv2_dw"],
        )
        self.conv_23 = Depth_Wise(
            keep["conv2_dw"], keep["conv_23"], kernel=(3, 3), stride=(2, 2),
            padding=(1, 1), groups=keep["conv_23"],
        )
        self.conv_3 = Residual(
            keep["conv_3"][0], num_block=len(keep["conv_3"]),
            groups=keep["conv_3"][0][1], kernel=(3, 3), stride=(1, 1),
            padding=(1, 1),
        )
        self.conv_34 = Depth_Wise(
            keep["conv_3"][0][0], keep["conv_34"], kernel=(3, 3),
            stride=(2, 2), padding=(1, 1), groups=keep["conv_34"],
        )
        self.conv_4 = Residual(
            keep["conv_4"][0], num_block=len(keep["conv_4"]),
            groups=keep["conv_4"][0][1], kernel=(3, 3), stride=(1, 1),
            padding=(1, 1),
        )
        self.conv_45 = Depth_Wise(
            keep["conv_4"][0][0], keep["conv_45"], kernel=(3, 3),
            stride=(2, 2), padding=(1, 1), groups=keep["conv_45"],
        )
        self.conv_5 = Residual(
            keep["conv_5"][0], num_block=len(keep["conv_5"]),
            groups=keep["conv_5"][0][1], kernel=(3, 3), stride=(1, 1),
            padding=(1, 1),
        )
        self.conv_6_sep = Conv_block(
            keep["conv_5"][0][0], keep["conv_6_sep"], kernel=(1, 1),
            stride=(1, 1), padding=(0, 0),
        )
        self.conv_6_dw = Linear_block(
            keep["conv_6_sep"], keep["conv_6_sep"], kernel=conv6_kernel,
            stride=(1, 1), padding=(0, 0), groups=keep["conv_6_sep"],
        )
        self.conv_6_flatten = Flatten()
        self.linear = nn.Linear(keep["conv_6_sep"], embedding_size, bias=False)
        self.bn = nn.BatchNorm1d(embedding_size)
        self.drop = nn.Dropout(p=drop_p)
        self.prob = nn.Linear(embedding_size, num_classes, bias=False)

    def forward(self, x):
        out = self.conv1(x)
        out = self.conv2_dw(out)
        out = self.conv_23(out)
        out = self.conv_3(out)
        out = self.conv_34(out)
        out = self.conv_4(out)
        out = self.conv_45(out)
        out = self.conv_5(out)
        out = self.conv_6_sep(out)
        out = self.conv_6_dw(out)
        out = self.conv_6_flatten(out)
        out = self.linear(out)
        out = self.bn(out)
        out = self.drop(out)
        out = self.prob(out)
        return out


class MiniFASNetSE(nn.Module):
    """MiniFASNet with Squeeze-and-Excitation attention blocks."""

    def __init__(self, keep, embedding_size=128, conv6_kernel=(5, 5),
                 drop_p=0.75, num_classes=3, img_channel=3):
        super().__init__()
        self.conv1 = Conv_block(
            img_channel, keep["conv1"], kernel=(3, 3), stride=(2, 2),
            padding=(1, 1),
        )
        self.conv2_dw = Conv_block(
            keep["conv1"], keep["conv2_dw"], kernel=(3, 3), stride=(1, 1),
            padding=(1, 1), groups=keep["conv2_dw"],
        )
        self.conv_23 = Depth_Wise(
            keep["conv2_dw"], keep["conv_23"], kernel=(3, 3), stride=(2, 2),
            padding=(1, 1), groups=keep["conv_23"],
        )
        self.conv_3 = ResidualSE(
            keep["conv_3"][0], num_block=len(keep["conv_3"]),
            groups=keep["conv_3"][0][1], kernel=(3, 3), stride=(1, 1),
            padding=(1, 1),
        )
        self.conv_34 = Depth_Wise(
            keep["conv_3"][0][0], keep["conv_34"], kernel=(3, 3),
            stride=(2, 2), padding=(1, 1), groups=keep["conv_34"],
        )
        self.conv_4 = ResidualSE(
            keep["conv_4"][0], num_block=len(keep["conv_4"]),
            groups=keep["conv_4"][0][1], kernel=(3, 3), stride=(1, 1),
            padding=(1, 1),
        )
        self.conv_45 = Depth_Wise(
            keep["conv_4"][0][0], keep["conv_45"], kernel=(3, 3),
            stride=(2, 2), padding=(1, 1), groups=keep["conv_45"],
        )
        self.conv_5 = ResidualSE(
            keep["conv_5"][0], num_block=len(keep["conv_5"]),
            groups=keep["conv_5"][0][1], kernel=(3, 3), stride=(1, 1),
            padding=(1, 1),
        )
        self.conv_6_sep = Conv_block(
            keep["conv_5"][0][0], keep["conv_6_sep"], kernel=(1, 1),
            stride=(1, 1), padding=(0, 0),
        )
        self.conv_6_dw = Linear_block(
            keep["conv_6_sep"], keep["conv_6_sep"], kernel=conv6_kernel,
            stride=(1, 1), padding=(0, 0), groups=keep["conv_6_sep"],
        )
        self.conv_6_flatten = Flatten()
        self.linear = nn.Linear(keep["conv_6_sep"], embedding_size, bias=False)
        self.bn = nn.BatchNorm1d(embedding_size)
        self.drop = nn.Dropout(p=drop_p)
        self.prob = nn.Linear(embedding_size, num_classes, bias=False)

    def forward(self, x):
        out = self.conv1(x)
        out = self.conv2_dw(out)
        out = self.conv_23(out)
        out = self.conv_3(out)
        out = self.conv_34(out)
        out = self.conv_4(out)
        out = self.conv_45(out)
        out = self.conv_5(out)
        out = self.conv_6_sep(out)
        out = self.conv_6_dw(out)
        out = self.conv_6_flatten(out)
        out = self.linear(out)
        out = self.bn(out)
        out = self.drop(out)
        out = self.prob(out)
        return out


# ---------------------------------------------------------------------------
# Convenience constructors (match Silent-Face naming)
# ---------------------------------------------------------------------------

def MiniFASNetV1(embedding_size=128, conv6_kernel=(5, 5),
                 num_classes=3, img_channel=3):
    return MiniFASNet(keep_dict["1.8M"], embedding_size, conv6_kernel,
                      drop_p=0.2, num_classes=num_classes,
                      img_channel=img_channel)


def MiniFASNetV2(embedding_size=128, conv6_kernel=(5, 5),
                 num_classes=3, img_channel=3):
    return MiniFASNet(keep_dict["1.8M_"], embedding_size, conv6_kernel,
                      drop_p=0.2, num_classes=num_classes,
                      img_channel=img_channel)


def MiniFASNetV1SE(embedding_size=128, conv6_kernel=(5, 5),
                   num_classes=3, img_channel=3):
    return MiniFASNetSE(keep_dict["1.8M"], embedding_size, conv6_kernel,
                        drop_p=0.75, num_classes=num_classes,
                        img_channel=img_channel)


def MiniFASNetV2SE(embedding_size=128, conv6_kernel=(5, 5),
                   num_classes=3, img_channel=3):
    return MiniFASNetSE(keep_dict["1.8M_"], embedding_size, conv6_kernel,
                        drop_p=0.75, num_classes=num_classes,
                        img_channel=img_channel)
