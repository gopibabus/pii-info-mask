"""Gradio UI: upload a document, get it back with PII replaced by [LABEL] tags."""

import tempfile
from collections import Counter
from html import escape
from pathlib import Path

import gradio as gr

from . import model
from .detect import MODEL_LABELS, PATTERN_LABELS, Span
from .documents import SUPPORTED, mask_file

STATIC = Path(__file__).parent / "static"
# Every label gets the one data hue; the inline tag names the kind.
COLOR_MAP = {label: "#1d5fbf" for label in [*MODEL_LABELS.values(), *PATTERN_LABELS.values()]}
KINDS = {
    "PERSON": "Names of people",
    "ADDRESS": "Postal addresses",
    "EMAIL": "Email addresses",
    "PHONE": "Phone numbers",
    "URL": "Web addresses",
    "DATE": "Dates",
    "ACCOUNT_NUMBER": "Account numbers",
    "SECRET": "Passwords, keys",
    "CREDIT_CARD": "Card numbers",
    "SSN": "US SSNs",
    "IBAN": "Bank accounts",
    "IP_ADDRESS": "IP addresses",
}
EMPTY_PREVIEW = (
    '<div class="kinds"><p>Upload a document and select Mask PII. Its text appears here with '
    "every detected item marked. Each one is replaced in the masked copy by its label:</p><ul>"
    + "".join(f'<li><span class="tag">{label}</span>{text}</li>' for label, text in KINDS.items())
    + "</ul></div>"
)
EMPTY_SUMMARY = '<div class="summary"><p class="summary-empty">No document masked yet.</p></div>'

MARK = (
    '<svg class="mark" viewBox="0 0 24 24" aria-hidden="true">'
    '<rect width="24" height="24" rx="6" fill="currentColor"/>'
    '<rect x="5" y="7" width="9" height="3" rx="1" fill="#fff"/>'
    '<rect x="5" y="14" width="14" height="3" rx="1" fill="#fff"/></svg>'
)
TOPBAR = f"""
<header class="topbar">
  <span class="brand">{MARK}PII Mask</span>
  <span class="status"><span class="dot" aria-hidden="true"></span>Runs on this machine</span>
</header>
"""
TITLE = """
<div class="title-row">
  <h1>Mask a document</h1>
  <p>Names, emails, phone numbers, addresses, account numbers and IDs are replaced with labels
  such as [PERSON]. Nothing is sent anywhere.</p>
</div>
"""


def _head() -> str:
    font = f"/gradio_api/file={STATIC / 'fonts' / 'Geist-Variable.woff2'}"
    return (
        "<style>@font-face{font-family:Geist;font-weight:100 900;font-display:swap;"
        f"src:url('{font}') format('woff2');}}</style>"
    )


def _highlight(text: str, spans: list[Span]) -> list[tuple[str, str | None]]:
    parts, pos = [], 0
    for span in spans:
        parts.append((text[pos : span.start], None))
        parts.append((text[span.start : span.end], span.label))
        pos = span.end
    parts.append((text[pos:], None))
    return [p for p in parts if p[0]]


def _summary(spans: list[Span], warnings: list[str]) -> str:
    counts = Counter(s.label for s in spans)
    total = sum(counts.values())
    top = max(counts.values(), default=1)
    rows = "".join(
        f'<li><span class="kind">{label.replace("_", " ").capitalize()}</span>'
        f'<span class="n">{n}</span>'
        f'<span class="bar" style="width:{n / top * 100:.0f}%"></span></li>'
        for label, n in counts.most_common()
    )
    notes = "".join(f'<p class="notice">{escape(w)}</p>' for w in warnings)
    noun = "item" if total == 1 else "items"
    return (
        f'<div class="summary"><p class="summary-total"><span class="figure">{total}</span> '
        f"{noun} masked</p><ul>{rows}</ul>{notes}</div>"
    )


def process(path: str | None):
    if not path:
        raise gr.Error("Upload a document first.")
    src = Path(path)
    dst = Path(tempfile.mkdtemp()) / f"{src.stem}.masked{src.suffix.lower()}"
    try:
        result = mask_file(src, dst)
    except ValueError as e:
        raise gr.Error(str(e)) from e

    return (
        _summary(result.spans, result.warnings),
        gr.HTML(visible=False),
        gr.HighlightedText(_highlight(result.text, result.spans), visible=True),
        gr.File(value=str(dst), visible=True),
    )


def build() -> gr.Blocks:
    gr.set_static_paths([STATIC])
    with gr.Blocks(title="PII Mask") as demo:
        gr.HTML(TOPBAR)
        gr.HTML(TITLE)
        with gr.Row(equal_height=False, elem_id="workspace"):
            with gr.Column(scale=1, min_width=320, elem_id="controls"):
                upload = gr.File(label="Document", file_types=list(SUPPORTED), type="filepath")
                run = gr.Button("Mask PII", variant="primary")
                summary = gr.HTML(EMPTY_SUMMARY)
                download = gr.File(label="Masked document", visible=False)
            with gr.Column(scale=2, min_width=420):
                gr.HTML(
                    '<div class="panel-head"><h2>Review</h2><p>Detection is automated and can '
                    "miss items. Read the marked text before you share the file.</p></div>"
                )
                empty = gr.HTML(EMPTY_PREVIEW)
                preview = gr.HighlightedText(
                    show_label=False,
                    visible=False,
                    color_map=COLOR_MAP,
                    combine_adjacent=False,
                    elem_id="preview",
                )
        run.click(process, inputs=upload, outputs=[summary, empty, preview, download])
    return demo


THEME = gr.themes.Base(
    font=[gr.themes.Font(f) for f in ("Geist", "system-ui", "sans-serif")],
    font_mono=[gr.themes.Font(f) for f in ("ui-monospace", "Menlo", "monospace")],
).set(
    body_background_fill="#f2f4f7",
    body_text_color="#0a0a0a",
    body_text_color_subdued="#5f6368",
    background_fill_primary="#ffffff",
    background_fill_secondary="#f2f4f7",
    block_background_fill="#ffffff",
    block_border_color="#e6e6e6",
    block_border_width="1px",
    block_radius="8px",
    block_shadow="none",
    block_label_background_fill="transparent",
    block_label_border_width="0px",
    block_label_text_color="#0a0a0a",
    block_label_text_size="14px",
    block_label_text_weight="500",
    border_color_primary="#e6e6e6",
    color_accent="#1d5fbf",
    color_accent_soft="#e8eef8",
    input_radius="6px",
    button_large_radius="6px",
    button_medium_radius="6px",
    button_primary_background_fill="#141414",
    button_primary_background_fill_hover="#333333",
    button_primary_text_color="#ffffff",
    button_primary_border_color="#141414",
    button_primary_shadow="none",
    button_primary_shadow_hover="none",
    loader_color="#1d5fbf",
)
# Light only: the dark variants take the light values, so a dark OS setting changes nothing.
for _name in [k for k in vars(THEME) if k.endswith("_dark")]:
    setattr(THEME, _name, getattr(THEME, _name.removesuffix("_dark")))
LAUNCH_KW = dict(theme=THEME, css_paths=[STATIC / "app.css"], head=_head(), footer_links=[])


def main() -> None:
    model.warm_up()
    # Gradio binds to 127.0.0.1 unless GRADIO_SERVER_NAME is set (the Docker image sets 0.0.0.0).
    build().launch(**LAUNCH_KW)
