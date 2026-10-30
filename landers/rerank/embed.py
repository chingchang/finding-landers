"""The frozen encoder. torch and transformers are only needed here: ``uv run --group rerank``."""

from __future__ import annotations

import numpy as np

MODEL = "facebook/dinov2-small"
REVISION = "ed25f3a31f01632728cabb09d1542f84ab7b0056"
MAX_CROPS = 80_000  # the protocol's hard cap on one pass
INPUT_PX = 224
MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)


class CapReached(RuntimeError):
    pass


class Dino:
    """``__call__(views)``: per crop, a list of windows as arrays in [0, 1]; returns float32 (n crops, 1536)."""

    def __init__(self, cache_dir: str, batch: int = 16, max_crops: int = MAX_CROPS):
        import torch
        from transformers import AutoModel

        self.torch = torch
        self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        self.model = AutoModel.from_pretrained(MODEL, revision=REVISION, cache_dir=cache_dir).to(self.device).eval()
        self.revision = REVISION
        self.batch, self.max_crops, self.crops = batch, max_crops, 0
        self.mean = torch.tensor(MEAN, device=self.device).reshape(1, 3, 1, 1)
        self.std = torch.tensor(STD, device=self.device).reshape(1, 3, 1, 1)

    def _forward(self, windows: list[np.ndarray]) -> np.ndarray:
        torch = self.torch
        out = []
        for i in range(0, len(windows), self.batch):
            x = torch.from_numpy(np.stack(windows[i : i + self.batch])).float().to(self.device)[:, None]
            x = torch.nn.functional.interpolate(x, size=(INPUT_PX, INPUT_PX), mode="bilinear", align_corners=False)
            x = (x.repeat(1, 3, 1, 1) - self.mean) / self.std
            with torch.no_grad():
                h = self.model(pixel_values=x).last_hidden_state
            grid = int(round((h.shape[1] - 1) ** 0.5))
            patches = h[:, 1:].reshape(len(x), grid, grid, -1)
            m = grid // 2
            centre = patches[:, m - 1 : m + 1, m - 1 : m + 1].mean(dim=(1, 2))
            out.append(torch.cat([h[:, 0], centre], dim=1).float().cpu().numpy())
        return np.concatenate(out)

    def __call__(self, views: list[list[np.ndarray]]) -> np.ndarray:
        self.crops += len(views)
        if self.crops > self.max_crops:
            raise CapReached(f"{self.crops} crops is over the cap of {self.max_crops}")
        parts = []
        for k in range(len(views[0])):
            windows = [v[k] for v in views]
            parts.append(self._forward(windows))
        return np.concatenate(parts, axis=1)
