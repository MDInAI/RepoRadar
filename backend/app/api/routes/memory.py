from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.api.deps import get_memory_service
from app.schemas.memory import MemorySegmentResponse, MemorySegmentWriteRequest
from app.services.memory_service import MemoryService

router = APIRouter()


@router.post(
    "/obsession/contexts/{context_id}/memory",
    response_model=MemorySegmentResponse,
    status_code=201,
)
def write_memory_segment(
    context_id: Annotated[int, Path(ge=1)],
    request: MemorySegmentWriteRequest,
    memory_service: Annotated[MemoryService, Depends(get_memory_service)],
) -> MemorySegmentResponse:
    """Write or update a memory segment for an obsession context."""
    segment = memory_service.write_memory(
        obsession_context_id=context_id,
        segment_key=request.segment_key,
        content=request.content,
        content_type=request.content_type,
    )
    return MemorySegmentResponse(
        id=segment.id,
        segment_key=segment.segment_key,
        content=segment.content,
        content_type=segment.content_type,
        created_at=segment.created_at,
        updated_at=segment.updated_at,
    )


@router.get(
    "/obsession/contexts/{context_id}/memory",
    response_model=list[MemorySegmentResponse],
)
def list_memory_segments(
    context_id: Annotated[int, Path(ge=1)],
    memory_service: Annotated[MemoryService, Depends(get_memory_service)],
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[MemorySegmentResponse]:
    """List all memory segments for an obsession context with optional pagination."""
    segments = memory_service.list_memory(
        obsession_context_id=context_id,
        limit=limit,
        offset=offset,
    )
    return [
        MemorySegmentResponse(
            id=seg.id,
            segment_key=seg.segment_key,
            content=seg.content,
            content_type=seg.content_type,
            created_at=seg.created_at,
            updated_at=seg.updated_at,
        )
        for seg in segments
    ]


@router.get(
    "/obsession/contexts/{context_id}/memory/{segment_key}",
    response_model=MemorySegmentResponse,
)
def read_memory_segment(
    context_id: Annotated[int, Path(ge=1)],
    segment_key: str,
    memory_service: Annotated[MemoryService, Depends(get_memory_service)],
) -> MemorySegmentResponse:
    """Read a specific memory segment by key."""
    segment = memory_service.read_memory(
        obsession_context_id=context_id,
        segment_key=segment_key,
    )
    return MemorySegmentResponse(
        id=segment.id,
        segment_key=segment.segment_key,
        content=segment.content,
        content_type=segment.content_type,
        created_at=segment.created_at,
        updated_at=segment.updated_at,
    )


@router.delete(
    "/obsession/contexts/{context_id}/memory/{segment_key}",
    status_code=204,
)
def delete_memory_segment(
    context_id: Annotated[int, Path(ge=1)],
    segment_key: str,
    memory_service: Annotated[MemoryService, Depends(get_memory_service)],
) -> None:
    """Delete a memory segment by key."""
    memory_service.delete_memory(
        obsession_context_id=context_id,
        segment_key=segment_key,
    )
