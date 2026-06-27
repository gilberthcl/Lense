"""
Model-fit guidance — surface when a stage is running on a model that is likely
too weak for heavy structured extraction.

This is advisory, not a gate: small / assistant-style models (e.g. ZySec /
SecurityLLM 7B) can answer chat well but routinely fail to emit the strict,
deeply-nested JSON the analyst stage needs — producing parse errors or empty
"shell" findings that look like a clean run but carry nothing. When we detect
that symptom we attach a plain-language recommendation pointing at the vetted
structural workhorses, so the operator knows to switch models rather than chase
a phantom bug.

Pure + dependency-light: catalog metadata + a name heuristic, no Ollama calls.
"""
from __future__ import annotations

import re

from app.services import model_catalog

# Below this many billions of parameters a general model tends to struggle with
# the analyst stage's long, strictly-typed JSON. Specialists can punch above
# their size, so this is only ONE input to the warning (the trigger is the
# observed parse failure / empty output, not size alone).
_WEAK_PARAM_B = 12.0

# Models we know are assistant/chat-tuned rather than extraction-tuned. Even at
# a respectable size these favour prose over strict JSON.
_ASSISTANT_HINTS = ("securityllm", "zysec")

# What to switch to — the vetted catalog models strong at structured extraction.
_RECOMMENDED = "gemma3:27b (structural workhorse) or Foundation-Sec-8B"


def params_b(model_name: str | None) -> float | None:
    """Approximate parameter count in billions, from the catalog if known, else
    parsed from the name (e.g. 'foo-7b', '20B'). None when undeterminable."""
    if not model_name:
        return None
    entry = model_catalog.by_ref(model_name)
    raw = entry.get("params") if entry else None
    if not raw:
        m = re.search(r"(\d+(?:\.\d+)?)\s*([bBmM])", model_name)
        raw = f"{m.group(1)}{m.group(2)}" if m else None
    if not raw:
        return None
    m = re.match(r"\s*(\d+(?:\.\d+)?)\s*([bBmM])", str(raw))
    if not m:
        return None
    val = float(m.group(1))
    return val / 1000.0 if m.group(2).lower() == "m" else val


def is_assistant_style(model_name: str | None) -> bool:
    n = (model_name or "").lower()
    return any(h in n for h in _ASSISTANT_HINTS)


def is_weak_for_extraction(model_name: str | None) -> bool:
    """True if this model is a likely-poor fit for the strict-JSON analyst stage:
    an assistant-style model, or a small (< ~12B) generalist."""
    if is_assistant_style(model_name):
        return True
    p = params_b(model_name)
    return p is not None and p < _WEAK_PARAM_B


def extraction_warning(model_name: str | None, *, parse_error: bool, empty: bool) -> str | None:
    """A plain-language recommendation when a weak model produced the tell-tale
    symptom (unparseable output or no substantive findings). None when the model
    looks adequate or there was no symptom — we don't nag a model that worked."""
    if not (parse_error or empty):
        return None
    if not is_weak_for_extraction(model_name):
        return None
    label = model_name or "the configured model"
    why = (
        "returned output that couldn't be parsed into findings"
        if parse_error
        else "produced no usable findings (empty result)"
    )
    style = (
        "It is an assistant/chat-tuned model, which favours prose over the strict "
        "JSON this stage needs."
        if is_assistant_style(model_name)
        else "It is a small model, which often can't hold the strict JSON structure "
        "this stage needs."
    )
    return (
        f"The analyst model '{label}' {why}. {style} "
        f"For this client's analysis stage, switch to {_RECOMMENDED} "
        "(Config → Models / the client's model setting). Re-analysing on a "
        "stronger model usually resolves empty or unparseable findings."
    )


def weak_model_suffix(model_name: str | None) -> str:
    """A short recommendation suffix to append to a 'could not reconstruct /
    structure the finding' error, when the configured model is a likely-weak
    fit. Empty when the model looks adequate (so we don't misattribute a genuine
    too-little-detail case to the model)."""
    if not is_weak_for_extraction(model_name):
        return ""
    label = model_name or "the configured model"
    return (
        f" Note: this client runs on '{label}', "
        + (
            "an assistant/chat-tuned model"
            if is_assistant_style(model_name)
            else "a small model"
        )
        + f" that often can't structure findings reliably — switching to "
        f"{_RECOMMENDED} usually fixes this."
    )
