"""Intent classification API endpoints for Phase 3.1."""

import logging
from typing import Any
from fastapi import APIRouter, Depends, status
from backend.app.core.security import get_current_user
from backend.app.learning.selection_provider import scoped_classifier
from backend.app.learning.shadow import observe_shadow
from backend.app.learning.routing import scoped_router

from backend.app.schemas.intent import (
    IntentClassificationRequest,
    IntentClassificationResponse,
)
from backend.app.services.intent_classification_service import (
    IntentClassificationService,
    get_intent_classification_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/intent", tags=["Intent Classifier"])


@router.post(
    "/classify",
    response_model=IntentClassificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Classify natural language query into structured intent",
)
async def classify_intent(
    request: IntentClassificationRequest,
    service: IntentClassificationService = Depends(get_intent_classification_service),
    current_user: Any = Depends(get_current_user),
) -> IntentClassificationResponse:
    """Analyze incoming user query and return classified intent with confidence and required agents."""
    logger.info("Received intent classification request: %s", request.query[:50])
    service = scoped_classifier(service, str(current_user.id), request.dataset_id)
    result = await scoped_router(service, str(current_user.id)).classify(
        query=request.query,
        context=request.context,
        dataset_id=request.dataset_id,
    )
    await observe_shadow(actor_id=str(current_user.id), dataset_id=request.dataset_id,
        question=request.query, live_intent=result.intent, source="intent_api")
    return result
