from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .protocol import ProtocolError

REPEAT_LIMIT = 2
FINDING_FIELDS = {"code", "scope", "message", "evidence"}


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProtocolError(field, "must be a non-empty string", value)
    return " ".join(value.split())


def _hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def finding_signature(payload: Mapping[str, Any]) -> tuple[str, str, str]:
    values = payload.get("findings")
    if not isinstance(values, list) or not values:
        raise ProtocolError("event.payload.findings", "REVISE requires at least one structured finding")
    identities: list[tuple[str, str]] = []
    evidence: list[tuple[str, str, str]] = []
    messages: list[str] = []
    for index, value in enumerate(values):
        field = f"event.payload.findings[{index}]"
        if not isinstance(value, dict) or set(value) != FINDING_FIELDS:
            raise ProtocolError(field, "must contain code, scope, message and evidence")
        code = _text(value["code"], f"{field}.code").upper()
        scope = _text(value["scope"], f"{field}.scope").lower()
        message = _text(value["message"], f"{field}.message")
        proof = _text(value["evidence"], f"{field}.evidence")
        identities.append((code, scope))
        evidence.append((code, scope, proof.lower()))
        messages.append(f"{code}@{scope}: {message}")
    if len(identities) != len(set(identities)):
        raise ProtocolError("event.payload.findings", "duplicate finding identity")
    return _hash(sorted(identities)), _hash(sorted(evidence)), "; ".join(messages)


def record_revise(state: dict[str, Any], key: str, revision: int, payload: Mapping[str, Any]) -> tuple[bool, str]:
    fingerprint, evidence_digest, summary = finding_signature(payload)
    previous = state["convergence"].get(key)
    repeats = 1
    if previous and previous["fingerprint"] == fingerprint and previous["evidence_digest"] == evidence_digest:
        repeats = previous["repeats"] + 1
    state["convergence"][key] = {
        "fingerprint": fingerprint,
        "evidence_digest": evidence_digest,
        "repeats": repeats,
        "last_revision": revision,
    }
    return repeats >= REPEAT_LIMIT, summary


def clear_review(state: dict[str, Any], key: str) -> None:
    state["convergence"].pop(key, None)
