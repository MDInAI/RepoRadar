from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from agentic_workers.storage.artifact_store import (
    activate_repository_artifacts,
    build_json_artifact,
    build_text_artifact,
)
from agentic_workers.storage.backend_models import RepositoryArtifactKind


def test_activate_repository_artifacts_rolls_back_partial_write_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_dir = tmp_path / "runtime"
    readme_path = runtime_dir / "data" / "readmes" / "101.md"
    analysis_path = runtime_dir / "data" / "analyses" / "101.json"
    readme_path.parent.mkdir(parents=True, exist_ok=True)
    analysis_path.parent.mkdir(parents=True, exist_ok=True)
    readme_path.write_text("old readme", encoding="utf-8")
    analysis_path.write_text('{"old": true}\n', encoding="utf-8")

    original_write_bytes = Path.write_bytes
    write_calls = {"count": 0}

    def fail_second_temp_write(self: Path, data: bytes) -> int:
        write_calls["count"] += 1
        if write_calls["count"] == 2:
            raise OSError("disk full")
        return original_write_bytes(self, data)

    monkeypatch.setattr(Path, "write_bytes", fail_second_temp_write)

    readme_artifact = build_text_artifact(
        runtime_relative_path="data/readmes/101.md",
        artifact_kind=RepositoryArtifactKind.README_SNAPSHOT,
        content="new readme",
        content_type="text/markdown; charset=utf-8",
        source_kind="repository_readme",
        source_url="https://api.github.com/repos/octocat/repo/readme",
        provenance_metadata={},
        generated_at=datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc),
    )
    analysis_artifact = build_json_artifact(
        runtime_relative_path="data/analyses/101.json",
        artifact_kind=RepositoryArtifactKind.ANALYSIS_RESULT,
        payload={"analysis": {"monetization_potential": "high"}},
        source_kind="repository_analysis",
        source_url="https://api.github.com/repos/octocat/repo/readme",
        provenance_metadata={},
        generated_at=datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc),
    )

    with pytest.raises(OSError, match="disk full"):
        activate_repository_artifacts(
            runtime_dir=runtime_dir,
            artifacts=[readme_artifact, analysis_artifact],
        )

    assert readme_path.read_text(encoding="utf-8") == "old readme"
    assert analysis_path.read_text(encoding="utf-8") == '{"old": true}\n'
