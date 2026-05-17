"""Exportiert hrnet_w32_horse10 → ONNX und verifiziert das Ergebnis."""
import torch
import torch.nn as nn
from mmpose.apis import init_model

CONFIG = "/app/models/horse10_hrnet_w32_1x.py"
CHECKPOINT = "/app/models/hrnet_w32_horse10_256x256_split1.pth"
OUTPUT = "/app/models/horse10_hrnet_w32.onnx"


class _PoseWrapper(nn.Module):
    def __init__(self, backbone, head):
        super().__init__()
        self.backbone = backbone
        self.head = head

    def forward(self, x):
        return self.head(self.backbone(x))


m = init_model(CONFIG, CHECKPOINT, device="cpu")
m.eval()
wrapper = _PoseWrapper(m.backbone, m.head)
wrapper.eval()

dummy = torch.randn(1, 3, 256, 256)
torch.onnx.export(
    wrapper,
    dummy,
    OUTPUT,
    input_names=["input"],
    output_names=["heatmaps"],
    dynamic_axes={"input": {0: "batch"}, "heatmaps": {0: "batch"}},
    opset_version=11,
)

import onnxruntime as ort
import numpy as np

sess = ort.InferenceSession(OUTPUT, providers=["CPUExecutionProvider"])
out = sess.run(None, {"input": dummy.numpy()})
assert out[0].shape == (1, 22, 64, 64), f"Unexpected shape: {out[0].shape}"
print(f"ONNX export + verify OK – shape: {out[0].shape}")
