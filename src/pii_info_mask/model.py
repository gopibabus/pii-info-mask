"""OpenAI Privacy Filter (int8 ONNX export) on ONNX Runtime.

The int8 export runs ~15x faster than the PyTorch weights on CPU with the same spans, and
needs no torch install. Files are fetched once into MODEL_DIR and reused on every later start.
"""

import json
import os
from functools import cache
from pathlib import Path

import numpy as np
import onnxruntime as ort
from huggingface_hub import snapshot_download
from tokenizers import Tokenizer

REPO = "openai/privacy-filter"
ONNX = "onnx/model_quantized.onnx"
FILES = ["config.json", "tokenizer.json", ONNX, ONNX + "_data"]
MODEL_DIR = Path(
    os.environ.get("PII_MODEL_DIR", Path.home() / ".cache" / "pii-info-mask" / "privacy-filter")
)


def ensure_downloaded() -> Path:
    """Download the model files unless every one of them is already in MODEL_DIR."""
    # huggingface_hub writes to a temp file and renames when done, so an existing file is complete.
    missing = [f for f in FILES if not (MODEL_DIR / f).is_file()]
    if missing:
        print(f"Downloading {REPO} ({', '.join(missing)}) to {MODEL_DIR} ...", flush=True)
        snapshot_download(REPO, local_dir=MODEL_DIR, allow_patterns=missing)
    else:
        print(f"Model found in {MODEL_DIR}; skipping download.", flush=True)
    return MODEL_DIR


@cache
def _load():
    model_dir = ensure_downloaded()
    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    session = ort.InferenceSession(
        str(model_dir / ONNX), options, providers=["CPUExecutionProvider"]
    )
    tokenizer = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
    config = json.loads((model_dir / "config.json").read_text())
    id2label = {int(k): v for k, v in config["id2label"].items()}
    return session, tokenizer, id2label


def warm_up() -> None:
    """Download if needed and load the session, so the first upload is not slow."""
    predict("My name is Alice Smith.")


def predict(text: str) -> list[tuple[int, int, str]]:
    """Return (start, end, category) spans by decoding the per-token BIOES tags."""
    session, tokenizer, id2label = _load()
    enc = tokenizer.encode(text)
    ids = np.array([enc.ids], dtype=np.int64)
    feeds = {"input_ids": ids, "attention_mask": np.ones_like(ids)}
    logits = session.run(None, {i.name: feeds[i.name] for i in session.get_inputs()})[0][0]

    spans, current = [], None
    for (start, end), label_id in zip(enc.offsets, logits.argmax(-1)):
        label = id2label[int(label_id)]
        if label == "O":
            current = None
            continue
        tag, category = label.split("-", 1)
        if tag in ("B", "S") or current is None or current[2] != category:
            current = [start, end, category]
            spans.append(current)
        else:
            current[1] = end
        if tag in ("E", "S"):
            current = None
    return [tuple(s) for s in spans]
