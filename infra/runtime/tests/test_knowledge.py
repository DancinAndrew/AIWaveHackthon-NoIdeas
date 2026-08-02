"""Contract tests for the Runtime-side Managed Knowledge Base reader.

The reader must always pin the querying agent's ``service_type`` metadata
filter, must never let retrieval失敗 break a conversational turn, and must
report honestly whether a query happened.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

RUNTIME_ROOT = Path(__file__).resolve().parents[1]
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from knowledge import (  # noqa: E402
    MAX_EXCERPT_LENGTH,
    KnowledgeBaseReader,
    NullKnowledgeBaseReader,
)


def _result(
    *,
    text: str = "先關閉總開關，再聯絡合格電匠。",
    service_type: str = "utility_repair",
    doc_kind: str = "safety",
    source_doc_id: str = "kb-utility-repair-001",
    uri: str = "s3://bucket/utility_repair/01-safety.md",
    score: float = 0.71,
) -> dict[str, Any]:
    return {
        "content": {"text": text, "type": "TEXT"},
        "metadata": {
            "service_type": service_type,
            "doc_kind": doc_kind,
            "source_doc_id": source_doc_id,
            "authoritative_scope": "static_only",
        },
        "location": {"type": "S3", "s3Location": {"uri": uri}},
        "score": score,
    }


class FakeRetrieveClient:
    def __init__(
        self,
        *,
        results: list[dict[str, Any]] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self._results = results if results is not None else [_result()]
        self._error = error

    def retrieve(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return {"retrievalResults": self._results}


class KnowledgeBaseReaderTests(unittest.TestCase):
    def test_retrieval_pins_the_agent_service_type_filter(self) -> None:
        client = FakeRetrieveClient()
        reader = KnowledgeBaseReader(
            client=client,
            knowledge_base_id="KB12345678",
            max_results=3,
        )

        result = reader.search(service_type="utility_repair", query="漏水要注意什麼")

        self.assertTrue(result.queried)
        self.assertEqual(result.outcome, "ok")
        self.assertEqual(len(client.calls), 1)
        call = client.calls[0]
        self.assertEqual(call["knowledgeBaseId"], "KB12345678")
        self.assertEqual(call["retrievalQuery"], {"text": "漏水要注意什麼"})
        vector_search = call["retrievalConfiguration"]["vectorSearchConfiguration"]
        self.assertEqual(vector_search["numberOfResults"], 3)
        self.assertEqual(
            vector_search["filter"],
            {"equals": {"key": "service_type", "value": "utility_repair"}},
        )

    def test_projected_reference_keeps_provenance_and_truncates_excerpt(self) -> None:
        long_text = "安" * (MAX_EXCERPT_LENGTH + 500)
        client = FakeRetrieveClient(results=[_result(text=long_text)])
        reader = KnowledgeBaseReader(client=client, knowledge_base_id="KB12345678")

        result = reader.search(service_type="utility_repair", query="安全規定")

        self.assertEqual(len(result.references), 1)
        reference = result.references[0]
        self.assertEqual(reference.service_type, "utility_repair")
        self.assertEqual(reference.doc_kind, "safety")
        self.assertEqual(reference.source_doc_id, "kb-utility-repair-001")
        self.assertEqual(
            reference.source_uri, "s3://bucket/utility_repair/01-safety.md"
        )
        self.assertEqual(reference.score, 0.71)
        self.assertLessEqual(len(reference.excerpt), MAX_EXCERPT_LENGTH)
        payload = reference.to_payload()
        self.assertEqual(payload["serviceType"], "utility_repair")
        self.assertEqual(payload["docKind"], "safety")
        self.assertEqual(payload["sourceDocId"], "kb-utility-repair-001")

    def test_cross_domain_chunks_are_dropped_even_when_returned(self) -> None:
        client = FakeRetrieveClient(
            results=[
                _result(service_type="community_consultation", doc_kind="notice"),
                _result(),
            ]
        )
        reader = KnowledgeBaseReader(client=client, knowledge_base_id="KB12345678")

        result = reader.search(service_type="utility_repair", query="規定")

        self.assertEqual(len(result.references), 1)
        self.assertEqual(result.references[0].service_type, "utility_repair")

    def test_empty_retrieval_is_reported_without_inventing_sources(self) -> None:
        client = FakeRetrieveClient(results=[])
        reader = KnowledgeBaseReader(client=client, knowledge_base_id="KB12345678")

        result = reader.search(service_type="utility_repair", query="規定")

        self.assertEqual(result.references, ())
        self.assertTrue(result.queried)
        self.assertEqual(result.outcome, "empty")

    def test_retrieval_failure_is_contained_and_reported(self) -> None:
        client = FakeRetrieveClient(error=RuntimeError("ThrottlingException"))
        reader = KnowledgeBaseReader(client=client, knowledge_base_id="KB12345678")

        result = reader.search(service_type="utility_repair", query="規定")

        self.assertEqual(result.references, ())
        self.assertTrue(result.queried)
        self.assertEqual(result.outcome, "failed")

    def test_blank_query_is_skipped_without_calling_the_service(self) -> None:
        client = FakeRetrieveClient()
        reader = KnowledgeBaseReader(client=client, knowledge_base_id="KB12345678")

        result = reader.search(service_type="utility_repair", query="   ")

        self.assertEqual(client.calls, [])
        self.assertFalse(result.queried)
        self.assertEqual(result.outcome, "skipped")

    def test_null_reader_never_claims_a_knowledge_query(self) -> None:
        reader = NullKnowledgeBaseReader()

        result = reader.search(service_type="utility_repair", query="規定")

        self.assertEqual(result.references, ())
        self.assertFalse(result.queried)
        self.assertEqual(result.outcome, "skipped")


if __name__ == "__main__":
    unittest.main()
