from app.core.errors import AppError
from app.repositories.memory_repository import MemoryRepository, MemorySegmentRecord
from app.repositories.obsession_repository import ObsessionRepository


class MemoryService:
    def __init__(
        self,
        memory_repo: MemoryRepository,
        obsession_repo: ObsessionRepository,
    ) -> None:
        self._memory_repo = memory_repo
        self._obsession_repo = obsession_repo

    def write_memory(
        self,
        obsession_context_id: int,
        segment_key: str,
        content: str,
        content_type: str,
    ) -> MemorySegmentRecord:
        context = self._obsession_repo.get_context(obsession_context_id)
        if not context:
            raise AppError(
                message=f"Obsession context {obsession_context_id} not found",
                code="obsession_context_not_found",
                status_code=404,
            )

        return self._memory_repo.write_segment(
            obsession_context_id=obsession_context_id,
            segment_key=segment_key,
            content=content,
            content_type=content_type,
        )

    def read_memory(
        self,
        obsession_context_id: int,
        segment_key: str,
    ) -> MemorySegmentRecord:
        context = self._obsession_repo.get_context(obsession_context_id)
        if not context:
            raise AppError(
                message=f"Obsession context {obsession_context_id} not found",
                code="obsession_context_not_found",
                status_code=404,
            )

        segment = self._memory_repo.read_segment(obsession_context_id, segment_key)
        if not segment:
            raise AppError(
                message=f"Memory segment '{segment_key}' not found",
                code="memory_segment_not_found",
                status_code=404,
            )

        return segment

    def list_memory(
        self,
        obsession_context_id: int,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[MemorySegmentRecord]:
        context = self._obsession_repo.get_context(obsession_context_id)
        if not context:
            raise AppError(
                message=f"Obsession context {obsession_context_id} not found",
                code="obsession_context_not_found",
                status_code=404,
            )

        return self._memory_repo.list_segments(obsession_context_id, limit, offset)

    def delete_memory(
        self,
        obsession_context_id: int,
        segment_key: str,
    ) -> bool:
        context = self._obsession_repo.get_context(obsession_context_id)
        if not context:
            raise AppError(
                message=f"Obsession context {obsession_context_id} not found",
                code="obsession_context_not_found",
                status_code=404,
            )

        deleted = self._memory_repo.delete_segment(obsession_context_id, segment_key)
        if not deleted:
            raise AppError(
                message=f"Memory segment '{segment_key}' not found",
                code="memory_segment_not_found",
                status_code=404,
            )

        return True
