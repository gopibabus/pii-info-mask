"""PII detection: OpenAI Privacy Filter for contextual PII, Presidio patterns for checksummed IDs."""

from dataclasses import dataclass
from functools import cache

from presidio_analyzer.predefined_recognizers import (
    CreditCardRecognizer,
    IbanRecognizer,
    IpRecognizer,
    UsSsnRecognizer,
)

from . import model

MODEL_LABELS = {
    "private_person": "PERSON",
    "private_address": "ADDRESS",
    "private_email": "EMAIL",
    "private_phone": "PHONE",
    "private_url": "URL",
    "private_date": "DATE",
    "account_number": "ACCOUNT_NUMBER",
    "secret": "SECRET",
}
PATTERN_LABELS = {
    "CREDIT_CARD": "CREDIT_CARD",
    "US_SSN": "SSN",
    "IBAN_CODE": "IBAN",
    "IP_ADDRESS": "IP_ADDRESS",
}
PATTERN_MIN_SCORE = 0.5
# Banded attention sees ~257 tokens, so chunks this size keep the context the model uses,
# while the export's attention cost grows quadratically with length (measured: 2k chars is the
# sweet spot; 10k-char chunks are several times slower per character).
CHUNK_CHARS = 2000


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    label: str


@cache
def _recognizers():
    return [CreditCardRecognizer(), UsSsnRecognizer(), IbanRecognizer(), IpRecognizer()]


def _chunks(text: str):
    """Yield (offset, chunk) pieces of at most ~CHUNK_CHARS, cut on newlines when possible."""
    start = 0
    while start < len(text):
        end = min(start + CHUNK_CHARS, len(text))
        if end < len(text):
            cut = text.rfind("\n", start, end)
            if cut > start:
                end = cut + 1
        yield start, text[start:end]
        start = end


def _model_spans(text: str) -> list[Span]:
    spans = []
    for offset, chunk in _chunks(text):
        if not chunk.strip():
            continue
        for start, end, category in model.predict(chunk):
            if label := MODEL_LABELS.get(category):
                spans.append(Span(offset + start, offset + end, label))
    return spans


def _pattern_spans(text: str) -> list[Span]:
    spans = []
    for recognizer in _recognizers():
        for result in recognizer.analyze(text, recognizer.supported_entities):
            if result.score >= PATTERN_MIN_SCORE:
                spans.append(Span(result.start, result.end, PATTERN_LABELS[result.entity_type]))
    return spans


def _normalize(text: str, span: Span) -> Span | None:
    """Strip surrounding whitespace, then widen to whole words so no partial word leaks."""
    start, end = span.start, span.end
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    if start == end:
        return None
    while start > 0 and text[start - 1].isalnum():
        start -= 1
    while end < len(text) and text[end].isalnum():
        end += 1
    return Span(start, end, span.label)


def _merge(text: str, spans: list[Span]) -> list[Span]:
    """Join fragments the pipeline splits (e.g. 'Alice' + 'Smith') and resolve overlaps.

    Same-label spans separated only by whitespace become one span. Overlapping spans
    of different labels collapse into one, keeping the label of the longer span
    (the earlier-listed span on a tie; detect() lists pattern spans first).
    """
    merged: list[Span] = []
    for span in sorted(spans, key=lambda s: (s.start, -s.end)):
        if merged:
            prev = merged[-1]
            touching = prev.label == span.label and not text[prev.end : span.start].strip()
            if span.start < prev.end or touching:
                longer = max(prev, span, key=lambda s: s.end - s.start)
                merged[-1] = Span(prev.start, max(prev.end, span.end), longer.label)
                continue
        merged.append(span)
    return merged


def detect(text: str) -> list[Span]:
    """Return non-overlapping PII spans in text, sorted by position."""
    # Pattern spans first: their checksum-validated labels (SSN, IBAN) win ties.
    normalized = (_normalize(text, s) for s in _pattern_spans(text) + _model_spans(text))
    return _merge(text, [s for s in normalized if s])


def mask_text(text: str, spans: list[Span]) -> str:
    out, pos = [], 0
    for span in spans:
        out.append(text[pos : span.start])
        out.append(f"[{span.label}]")
        pos = span.end
    out.append(text[pos:])
    return "".join(out)
