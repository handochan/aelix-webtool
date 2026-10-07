from __future__ import annotations

import pytest

from aelix_webtool.config import Config
from aelix_webtool.errors import WebToolError
from aelix_webtool.models import FindRequest, ReadRequest
from aelix_webtool.service import WebService
from aelix_webtool.store import SnapshotStore


def fixture_service():
    store = SnapshotStore()
    item = store.put(
        url="https://example.com/guide",
        requested_url="https://example.com/guide",
        title="Guide",
        content="첫 줄\nTimeout = 10\n두 번째 timeout 설명\nLiteral (a+)+ text",
        content_type="text/plain",
        format="text",
    )
    return WebService(Config(offline=True), store=store), item


def test_cached_reads_work_offline_and_return_original_unicode_positions():
    service, item = fixture_service()
    offset = item.content.index("Timeout")
    result = service.read(ReadRequest(item.snapshot_id, offset=offset, max_chars=100))
    assert result["content"] == item.content[offset : offset + 100]
    assert result["line_start"] == 2 and result["line_end"] == 4
    assert result["offset_unit"] == "unicode_codepoints"
    assert result["content_hash"] == item.content_hash


def test_find_case_and_literal_regex_are_source_grounded():
    service, item = fixture_service()
    result = service.find(FindRequest(item.snapshot_id, "TIMEOUT"))
    assert result["total_matches"] == 2
    for match in result["matches"]:
        assert item.content[match["start"] : match["end"]] == match["matched_text"]
        assert item.content[match["context_start"] : match["context_end"]] == match["context"]
    exact = service.find(FindRequest(item.snapshot_id, "Timeout", case_sensitive=True))
    assert exact["total_matches"] == 1
    literal = service.find(FindRequest(item.snapshot_id, "(a+)+"))
    assert literal["total_matches"] == 1
    assert literal["matches"][0]["line_start"] == 4


def test_find_bounds_and_missing_queries_are_explicit():
    service = WebService(Config())
    item = service.store.put(
        url="https://example.com/large",
        requested_url="https://example.com/large",
        title="Large",
        content="marker " * 5000,
        content_type="text/plain",
        format="text",
    )
    result = service.find(FindRequest(item.snapshot_id, "marker", max_matches=3))
    assert result["total_matches"] == 5000 and len(result["matches"]) == 3
    assert result["truncated"] is True and len(result["text"]) <= 16000
    assert service.find(FindRequest(item.snapshot_id, "absent"))["total_matches"] == 0


def test_snapshot_ids_are_instance_scoped_and_not_file_paths():
    service, item = fixture_service()
    other = WebService(Config())
    with pytest.raises(WebToolError) as exc:
        other.read(ReadRequest(item.snapshot_id))
    assert exc.value.code == "snapshot_not_found"
    for key in ["/etc/passwd", "../secret", "x" * 1000]:
        with pytest.raises(WebToolError):
            ReadRequest.from_args({"snapshot_id": key})


@pytest.mark.parametrize(
    "extra",
    [
        {"query": ""},
        {"query": "a\nb"},
        {"query": "x" * 201},
        {"case_sensitive": "true"},
        {"max_matches": 21},
        {"context_chars": 501},
    ],
)
def test_find_argument_bounds(extra):
    _, item = fixture_service()
    with pytest.raises(WebToolError):
        FindRequest.from_args({"snapshot_id": item.snapshot_id, "query": "ok", **extra})
