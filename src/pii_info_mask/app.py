"""Gradio UI: upload a document, get it back with PII replaced by [LABEL] tags."""

import tempfile
from collections import Counter
from pathlib import Path

import gradio as gr

from . import model
from .detect import Span
from .documents import SUPPORTED, mask_file


def _highlight(text: str, spans: list[Span]) -> list[tuple[str, str | None]]:
    parts, pos = [], 0
    for span in spans:
        parts.append((text[pos : span.start], None))
        parts.append((text[span.start : span.end], span.label))
        pos = span.end
    parts.append((text[pos:], None))
    return [p for p in parts if p[0]]


def process(path: str | None):
    if not path:
        raise gr.Error("Upload a document first.")
    src = Path(path)
    dst = Path(tempfile.mkdtemp()) / f"{src.stem}.masked{src.suffix.lower()}"
    try:
        result = mask_file(src, dst)
    except ValueError as e:
        raise gr.Error(str(e)) from e

    counts = Counter(s.label for s in result.spans)
    lines = [f"**{sum(counts.values())} PII items masked**"]
    lines += [f"- {label}: {n}" for label, n in counts.most_common()]
    lines += [f"⚠️ {w}" for w in result.warnings]
    return "\n".join(lines), _highlight(result.text, result.spans), str(dst)


def build() -> gr.Blocks:
    with gr.Blocks(title="PII Mask") as demo:
        gr.Markdown(
            "# PII Mask\nUpload a TXT, DOCX or PDF. PII is replaced with labels like `[PERSON]`. "
            "Everything runs on this machine.\n\n"
            "_Detection is automated and can miss items; review the preview before sharing._"
        )
        with gr.Row():
            with gr.Column(scale=1):
                upload = gr.File(label="Document", file_types=list(SUPPORTED), type="filepath")
                run = gr.Button("Mask PII", variant="primary")
                summary = gr.Markdown()
                download = gr.File(label="Masked document")
            with gr.Column(scale=2):
                preview = gr.HighlightedText(label="Detected PII", combine_adjacent=False)
        run.click(process, inputs=upload, outputs=[summary, preview, download])
    return demo


def main() -> None:
    model.warm_up()
    # Gradio binds to 127.0.0.1 unless GRADIO_SERVER_NAME is set (the Docker image sets 0.0.0.0).
    build().launch()
