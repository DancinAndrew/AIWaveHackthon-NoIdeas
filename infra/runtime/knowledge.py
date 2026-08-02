"""Managed Knowledge Base retrieval for the logical domain agents.

Every query pins the calling agent's ``service_type`` metadata filter, so a
domain agent can never read another domain's documents.  Retrieved chunks are
explanatory references only: prices, stock, availability, provider status and
case state must come from RDS-backed tools, never from here.

Retrieval is best effort.  A failed or empty query degrades to an empty result
with an honest outcome so a conversational turn, and especially a safety
warning, is never blocked by the knowledge base.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)

SERVICE_TYPE_METADATA_KEY = "service_type"
AUTHORITATIVE_SCOPE_METADATA_KEY = "authoritative_scope"
NEVER_AUTHORITATIVE_METADATA_KEY = "never_authoritative_for"
STATIC_ONLY_SCOPE = "static_only"
DEFAULT_MAX_RESULTS = 3
MAX_ALLOWED_RESULTS = 10
MAX_EXCERPT_LENGTH = 1_200
MAX_QUERY_LENGTH = 400
MAX_SUPPRESSION_RECORDS = 10

OUTCOME_OK = "ok"
OUTCOME_EMPTY = "empty"
OUTCOME_SKIPPED = "skipped"
OUTCOME_FAILED = "failed"
OUTCOME_SUPPRESSED = "suppressed"

# Platform default used when a chunk does not declare its own boundary. The
# vocabulary matches ``never_authoritative_for`` in data/mock/knowledge/*.md so a
# regenerated sidecar can narrow this per document without a code change.
DEFAULT_NEVER_AUTHORITATIVE_FIELDS = (
    "price",
    "fee_amounts",
    "inventory",
    "stock_eta",
    "availability",
    "table_inventory",
    "promotion_availability",
    "responsible_unit_availability",
    "technician_schedule",
    "staff_schedule",
    "menu",
    "case_status",
    "sla_actuals",
)

# A live-value question asks for a concrete current fact. A policy question asks
# what the rules are, which static documents are authoritative for, so a policy
# marker anywhere in the message stops detection.
POLICY_MARKERS = (
    "政策",
    "條款",
    "規定",
    "規約",
    "保固",
    "保障",
    "取消",
    "退款",
    "退費",
    "計費",
    "計價",
    "收費方式",
    "怎麼算",
)
LIVE_VALUE_TOPIC_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "price",
        ("多少錢", "報價", "價錢", "價格是", "要多少", "收多少", "費用是", "幾元"),
    ),
    ("inventory", ("有沒有貨", "還有貨", "有現貨", "缺貨", "庫存")),
    (
        "availability",
        ("可以約", "約得到", "訂得到", "有空嗎", "什麼時候有空", "還有位子", "可預約時段"),
    ),
    ("schedule", ("排班", "師傅有空", "誰會來", "哪位師傅")),
    ("case_status", ("到哪了", "處理到哪", "進度如何", "現在什麼狀態", "查進度")),
)
# Topic name -> the declared field names that make a chunk unusable for it.
TOPIC_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "price": ("price", "fee_amounts"),
    "inventory": ("inventory", "stock_eta", "table_inventory", "menu"),
    "availability": (
        "availability",
        "promotion_availability",
        "responsible_unit_availability",
    ),
    "schedule": ("technician_schedule", "staff_schedule"),
    "case_status": ("case_status", "sla_actuals"),
}


def detect_live_value_topics(message: str) -> tuple[str, ...]:
    """Topics in this message that only live structured data may answer."""

    text = message or ""
    if any(marker in text for marker in POLICY_MARKERS):
        return ()
    return tuple(
        topic
        for topic, terms in LIVE_VALUE_TOPIC_TERMS
        if any(term in text for term in terms)
    )


class RetrieveClient(Protocol):
    def retrieve(self, **kwargs: Any) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class KnowledgeReference:
    """One retrieved static chunk, projected for the runtime response."""

    service_type: str
    doc_kind: str
    excerpt: str
    source_doc_id: str | None = None
    source_uri: str | None = None
    score: float | None = None
    authoritative_scope: str | None = None
    never_authoritative_for: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "serviceType": self.service_type,
            "docKind": self.doc_kind,
            "sourceDocId": self.source_doc_id,
            "sourceUri": self.source_uri,
            "excerpt": self.excerpt,
            "score": self.score,
            "authoritativeScope": self.authoritative_scope,
        }


@dataclass(frozen=True, slots=True)
class SuppressedReference:
    """A chunk withheld because it may not answer this question.

    The excerpt is deliberately absent: recording the withheld text would put it
    back into prompts, traces and logs, which is what the boundary prevents.
    """

    doc_kind: str
    reason: str
    source_doc_id: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "sourceDocId": self.source_doc_id,
            "docKind": self.doc_kind,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class KnowledgeResult:
    """Retrieval outcome, including whether a query actually happened."""

    references: tuple[KnowledgeReference, ...] = ()
    queried: bool = False
    outcome: str = OUTCOME_SKIPPED
    live_value_topics: tuple[str, ...] = ()
    suppressed: tuple[SuppressedReference, ...] = ()

    def to_payload(self) -> list[dict[str, Any]]:
        return [reference.to_payload() for reference in self.references]


SKIPPED_RESULT = KnowledgeResult()


class KnowledgeBaseReader:
    """Query one Amazon Bedrock managed knowledge base with a domain filter."""

    def __init__(
        self,
        *,
        client: RetrieveClient,
        knowledge_base_id: str,
        max_results: int = DEFAULT_MAX_RESULTS,
    ) -> None:
        self._client = client
        self._knowledge_base_id = (knowledge_base_id or "").strip()
        self._max_results = max(1, min(int(max_results), MAX_ALLOWED_RESULTS))

    def search(self, *, service_type: str, query: str) -> KnowledgeResult:
        cleaned = (query or "").strip()[:MAX_QUERY_LENGTH]
        if not cleaned or not self._knowledge_base_id or not service_type:
            return SKIPPED_RESULT

        # Detected here rather than by the caller so the boundary cannot be
        # bypassed by forgetting to pass it in.
        live_value_topics = detect_live_value_topics(cleaned)

        try:
            response = self._client.retrieve(
                knowledgeBaseId=self._knowledge_base_id,
                retrievalQuery={"text": cleaned},
                retrievalConfiguration={
                    "vectorSearchConfiguration": {
                        "numberOfResults": self._max_results,
                        "filter": {
                            "equals": {
                                "key": SERVICE_TYPE_METADATA_KEY,
                                "value": service_type,
                            }
                        },
                    }
                },
            )
        except Exception as error:  # noqa: BLE001 - retrieval must never break a turn
            logger.warning(
                "knowledge base retrieval failed service_type=%s error_type=%s",
                service_type,
                type(error).__name__,
            )
            return KnowledgeResult(
                references=(),
                queried=True,
                outcome=OUTCOME_FAILED,
                live_value_topics=live_value_topics,
            )

        references, suppressed = self._project(
            response,
            service_type,
            live_value_topics,
        )
        if references:
            outcome = OUTCOME_OK
        elif suppressed:
            outcome = OUTCOME_SUPPRESSED
        else:
            outcome = OUTCOME_EMPTY
        return KnowledgeResult(
            references=references,
            queried=True,
            outcome=outcome,
            live_value_topics=live_value_topics,
            suppressed=suppressed,
        )

    def _project(
        self,
        response: Mapping[str, Any],
        service_type: str,
        live_value_topics: tuple[str, ...],
    ) -> tuple[tuple[KnowledgeReference, ...], tuple[SuppressedReference, ...]]:
        raw_results = response.get("retrievalResults")
        if not isinstance(raw_results, list):
            return (), ()

        references: list[KnowledgeReference] = []
        suppressed: list[SuppressedReference] = []
        for raw in raw_results:
            reference = _project_one(raw, service_type)
            if reference is None:
                continue
            reason = _suppression_reason(reference, live_value_topics)
            if reason is None:
                references.append(reference)
                continue
            logger.info(
                "knowledge chunk withheld service_type=%s doc_kind=%s reason=%s",
                service_type,
                reference.doc_kind,
                reason,
            )
            suppressed.append(
                SuppressedReference(
                    doc_kind=reference.doc_kind,
                    reason=reason,
                    source_doc_id=reference.source_doc_id,
                )
            )
        return (
            tuple(references[: self._max_results]),
            tuple(suppressed[:MAX_SUPPRESSION_RECORDS]),
        )


class NullKnowledgeBaseReader:
    """Stand-in used when no knowledge base is configured for the process."""

    def search(self, *, service_type: str, query: str) -> KnowledgeResult:
        return SKIPPED_RESULT


def _project_one(raw: Any, service_type: str) -> KnowledgeReference | None:
    if not isinstance(raw, Mapping):
        return None

    content = raw.get("content")
    text = content.get("text") if isinstance(content, Mapping) else None
    if not isinstance(text, str) or not text.strip():
        return None

    metadata = raw.get("metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    # Defence in depth: the request already filters on service_type, but a
    # mislabelled chunk must never surface inside another domain's answer.
    if metadata.get(SERVICE_TYPE_METADATA_KEY) != service_type:
        return None

    return KnowledgeReference(
        service_type=service_type,
        doc_kind=_optional_string(metadata.get("doc_kind")) or "unspecified",
        excerpt=text.strip()[:MAX_EXCERPT_LENGTH],
        source_doc_id=_optional_string(metadata.get("source_doc_id")),
        source_uri=_source_uri(raw.get("location")),
        score=_bounded_score(raw.get("score")),
        authoritative_scope=_optional_string(
            metadata.get(AUTHORITATIVE_SCOPE_METADATA_KEY)
        ),
        never_authoritative_for=_declared_fields(
            metadata.get(NEVER_AUTHORITATIVE_METADATA_KEY)
        ),
    )


def _declared_fields(value: Any) -> tuple[str, ...]:
    """Read a chunk's own boundary declaration, list or comma-separated."""

    if isinstance(value, str):
        parts = value.split(",")
    elif isinstance(value, (list, tuple)):
        parts = [str(item) for item in value]
    else:
        return ()
    return tuple(part.strip() for part in parts if part and part.strip())


def _suppression_reason(
    reference: KnowledgeReference,
    live_value_topics: tuple[str, ...],
) -> str | None:
    """Why this chunk may not answer the current question, if it may not."""

    if not live_value_topics:
        return None
    if reference.authoritative_scope != STATIC_ONLY_SCOPE:
        return None
    declared = set(reference.never_authoritative_for) or set(
        DEFAULT_NEVER_AUTHORITATIVE_FIELDS
    )
    for topic in live_value_topics:
        aliases = TOPIC_FIELD_ALIASES.get(topic, (topic,))
        if declared.intersection(aliases):
            return f"static_only_not_authoritative_for_{topic}"
    return None


def _source_uri(location: Any) -> str | None:
    if not isinstance(location, Mapping):
        return None
    s3_location = location.get("s3Location")
    if isinstance(s3_location, Mapping):
        return _optional_string(s3_location.get("uri"))
    return None


def _optional_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()[:2048]
    return None


def _bounded_score(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return max(0.0, min(float(value), 1.0))
