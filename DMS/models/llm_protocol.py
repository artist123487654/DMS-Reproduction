"""VLM 调用协议。"""

from __future__ import annotations

from typing import Any, Optional, Protocol

import numpy as np


class MultimodalLLM(Protocol):
    def predict_mm(
        self, text_prompt: str, images: list[np.ndarray]
    ) -> tuple[str, Optional[bool], Any]: ...
