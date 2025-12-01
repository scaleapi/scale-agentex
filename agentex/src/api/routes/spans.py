from fastapi import APIRouter

from src.api.schemas.spans import CreateSpanRequest, Span, UpdateSpanRequest
from src.domain.use_cases.spans_use_case import DSpanUseCase
from src.utils.logging import make_logger

logger = make_logger(__name__)

router = APIRouter(prefix="/spans", tags=["Spans"])


@router.post(
    "",
    response_model=Span,
)
async def create_span(
    request: CreateSpanRequest,
    span_use_case: DSpanUseCase,
) -> Span:
    """
    Create a new span with the provided parameters
    """
    return await span_use_case.create(
        id=request.id,
        trace_id=request.trace_id,
        name=request.name,
        parent_id=request.parent_id,
        start_time=request.start_time,
        end_time=request.end_time,
        input_data=request.input,
        output_data=request.output,
        data=request.data,
    )


@router.patch(
    "/{span_id}",
    response_model=Span,
)
async def partial_update_span(
    span_id: str,
    request: UpdateSpanRequest,
    span_use_case: DSpanUseCase,
) -> Span:
    """
    Update a span with the provided output data and mark it as complete
    """
    return await span_use_case.partial_update(
        id=span_id,
        trace_id=request.trace_id,
        name=request.name,
        parent_id=request.parent_id,
        start_time=request.start_time,
        end_time=request.end_time,
        input_data=request.input,
        output_data=request.output,
        data=request.data,
    )


@router.get(
    "/{span_id}",
    response_model=Span,
)
async def get_span(
    span_id: str,
    span_use_case: DSpanUseCase,
) -> Span:
    """
    Get a span by ID
    """
    span = await span_use_case.get(span_id=span_id)
    return span


@router.get(
    "",
    response_model=list[Span],
)
async def list_spans(
    span_use_case: DSpanUseCase,
    trace_id: str | None = None,
    limit: int = 50,
    page_number: int = 1,
    order_by: str | None = None,
    order_direction: str = "desc",
) -> list[Span]:
    """
    List all spans for a given trace ID
    """
    logger.info(f"Listing spans for trace ID: {trace_id}")
    spans = await span_use_case.list(
        trace_id=trace_id,
        limit=limit,
        page_number=page_number,
        order_by=order_by,
        order_direction=order_direction,
    )
    return [Span.model_validate(span) for span in spans]
