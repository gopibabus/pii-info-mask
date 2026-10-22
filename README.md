# pii-info-mask

A local web app that masks personal information (PII) in documents. Upload a TXT, DOCX or PDF and
download a copy where each PII item is replaced by a label such as `[PERSON]` or `[EMAIL]`.

Everything runs inside a Docker container on your own machine. No document is sent to any outside
service. The only network access is the one-time model download on first start.

## Requirements

- [Docker](https://docs.docker.com/get-docker/) with Docker Compose v2 (`docker compose`)
- About 3 GB of free disk space (≈0.9 GB image + 1.6 GB model)
- At least 4 GB of memory available to Docker (Docker Desktop: Settings → Resources)
- Internet access for the first build and first start

Works on Linux, macOS and Windows, on both x86-64 and ARM (including Apple Silicon).

## Quick start

```bash
git clone https://github.com/gopibabus/pii-info-mask.git
cd pii-info-mask
docker compose up -d --build
docker compose logs -f   # watch the first-start model download; Ctrl+C to stop watching
```

When the log shows `Running on local URL`, open http://localhost:7860, upload a document, click
**Mask PII**, and download the masked file.

## What gets downloaded, and when

**At build time** (`docker compose up --build`), Python packages pinned by `uv.lock`:

| Component | What it does |
|---|---|
| [ONNX Runtime](https://onnxruntime.ai/) | Runs the model on CPU |
| [Presidio](https://github.com/microsoft/presidio) pattern rules | Detect credit cards, SSNs, IBANs and IP addresses, with checksum validation |
| [Gradio](https://www.gradio.app/) | The web interface |
| PyMuPDF, python-docx | Read and write PDF and DOCX files |

**At first start**, the [OpenAI Privacy Filter](https://huggingface.co/openai/privacy-filter) model
(Apache 2.0, int8 ONNX export, ~1.6 GB). It detects names, addresses, emails, phone numbers, URLs,
dates, account numbers and secrets.

The model is saved in a Docker volume named `pii-info-mask_models`, not in the image and not in
this repository. On every later start the app finds it and skips the download:

```
Model found in /models; skipping download.
```

The volume survives `docker compose down` and image rebuilds. To force a fresh download, remove it:

```bash
docker compose down -v
```

If a download is interrupted, the next start downloads only the missing files.

## Everyday commands

```bash
docker compose up -d          # start in the background
docker compose logs -f        # follow logs
docker compose down           # stop and remove the container (model volume is kept)
docker compose up -d --build  # rebuild after pulling new code
```

## Performance

The model is loaded once at startup, so the first upload is as fast as later ones. Measured in
Docker on an Apple M1 (8 CPUs given to Docker):

| Document | Time |
|---|---|
| 1-page TXT / DOCX / PDF | under 1 second |
| 10 dense PDF pages (630 PII items) | about 10 seconds |

Choices behind these numbers:

- **ONNX Runtime with the int8 model.** In Docker the PyTorch build of the same model took ~40 s
  for a single paragraph; the int8 ONNX export gives the same results in a fraction of a second,
  and leaves PyTorch out of the image (0.9 GB instead of 4.6 GB).
- **Text is processed in ~2,000-character chunks.** The model only looks ~250 tokens around each
  word, and its cost grows faster than linearly with input length, so chunking is both faster and
  loses no context.
- **PDF redaction** searches each distinct value once per page.

More CPUs for Docker means faster processing of large documents.

## What gets masked

| Label | Source |
|---|---|
| `PERSON`, `ADDRESS`, `EMAIL`, `PHONE`, `URL`, `DATE`, `ACCOUNT_NUMBER`, `SECRET` | Privacy Filter model |
| `CREDIT_CARD`, `SSN`, `IBAN`, `IP_ADDRESS` | Presidio pattern rules |

How each format is handled:

| Format | Masking |
|---|---|
| TXT | Text replaced in place. |
| DOCX | Body, tables, headers and footers. Formatting such as bold or italic is kept. |
| PDF | True redaction: the underlying text is removed, and a black box with the label is drawn in its place. The rest of the page stays where it was. |

## Configuration

The port is published on `127.0.0.1` only, so other machines on your network cannot reach the app.
To change this, edit `ports` in `compose.yaml`:

```yaml
ports:
  - "8080:7860"   # serve on port 8080, reachable from your network
```

## Project layout

```
compose.yaml                    Docker Compose service and model volume
docker/Dockerfile               Image build: Python dependencies and app (no model)
docker/Dockerfile.dockerignore  Files kept out of the build context
src/pii_info_mask/model.py      Model download (skipped if present) and ONNX inference
src/pii_info_mask/detect.py     PII detection (model + pattern rules) and span merging
src/pii_info_mask/documents.py  Masking for TXT, DOCX and PDF
src/pii_info_mask/app.py        Gradio web UI
```

## Running without Docker

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv run pii-info-mask
```

The model is downloaded on first start to `~/.cache/pii-info-mask/privacy-filter`, or to the folder
in the `PII_MODEL_DIR` environment variable if set.

## Limitations

- Scanned PDF pages (images of text) are not masked. The app shows a warning when it finds one.
- Detection is automated and can miss items or mask too much. Always review the preview before
  sharing a masked document.
- Works best on English text.
- Privacy Filter is a data-minimization aid, not a guarantee of anonymization or legal compliance.
