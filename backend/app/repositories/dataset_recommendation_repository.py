"""Dataset recommendation repository providing CRUD operations for cleaning recommendations."""

import logging
from datetime import UTC, datetime
from typing import Any, List, Tuple

from fastapi import Depends
from sqlalchemy.orm import Session

from backend.app.database.postgres import get_db_session
from backend.app.models.dataset_recommendation import DatasetRecommendation

logger = logging.getLogger(__name__)


class DatasetRecommendationRepository:
    """Repository handling persistence and retrieval of DatasetRecommendation entities."""

    def __init__(self, db: Session | None = None) -> None:
        self.db = db

    @property
    def session(self) -> Session | None:
        """Return the bound session or None."""
        return self.db

    def _resolve_session(self, session: Session | None) -> Session:
        active_session = session or self.db
        if active_session is None:
            raise ValueError("A database session must be provided or bound to the repository")
        return active_session

    def create_many(
        self,
        arg1: Any,
        arg2: Any = None,
        session: Session | None = None,
    ) -> List[DatasetRecommendation]:
        """Persist multiple cleaning recommendations. Supports both (session, recs) and (recs, session=...)."""
        if isinstance(arg1, Session):
            active_session = arg1
            recommendations = arg2 or []
        else:
            recommendations = arg1 or []
            active_session = session or (arg2 if isinstance(arg2, Session) else self.db)

        if not recommendations:
            raise ValueError("Recommendation list cannot be empty")

        sess = self._resolve_session(active_session)
        try:
            sess.add_all(recommendations)
            sess.commit()
            for r in recommendations:
                sess.refresh(r)
            logger.info(
                "Created %d recommendations for dataset %s",
                len(recommendations),
                recommendations[0].dataset_id,
            )
            return recommendations
        except Exception as e:
            sess.rollback()
            logger.error("Failed to create recommendations: %s", e)
            raise ValueError(f"Failed to create recommendations: {e}") from e

    def get_by_dataset_and_version(
        self,
        dataset_id: str,
        version_id: str,
        status: str = "active",
        limit: int = 100,
        offset: int = 0,
        session: Session | None = None,
    ) -> Tuple[List[DatasetRecommendation], int]:
        """Retrieve paginated recommendations for a specific dataset and version."""
        sess = self._resolve_session(session)
        query = sess.query(DatasetRecommendation).filter(
            DatasetRecommendation.dataset_id == dataset_id,
            DatasetRecommendation.version_id == version_id,
            DatasetRecommendation.status == status,
        )
        total_count = query.count()
        recommendations = (
            query.order_by(DatasetRecommendation.priority_score.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )
        return recommendations, total_count

    def get_by_dataset(
        self,
        dataset_id: str,
        status: str = "active",
        severity_filter: List[str] | None = None,
        limit: int = 100,
        session: Session | None = None,
    ) -> List[DatasetRecommendation]:
        """Retrieve recommendations for a dataset with optional severity filtering."""
        sess = self._resolve_session(session)
        query = sess.query(DatasetRecommendation).filter(
            DatasetRecommendation.dataset_id == dataset_id,
            DatasetRecommendation.status == status,
        )
        if severity_filter:
            query = query.filter(DatasetRecommendation.severity.in_(severity_filter))
        return (
            query.order_by(
                DatasetRecommendation.priority_score.desc(),
                DatasetRecommendation.created_at.desc(),
            )
            .limit(limit)
            .all()
        )

    def get_active_recommendations_for_dataset(
        self,
        dataset_id: str,
        session: Session | None = None,
    ) -> List[DatasetRecommendation]:
        """Retrieve active recommendations ordered by priority score descending."""
        sess = self._resolve_session(session)
        return (
            sess.query(DatasetRecommendation)
            .filter(
                DatasetRecommendation.dataset_id == dataset_id,
                DatasetRecommendation.status == "active",
            )
            .order_by(DatasetRecommendation.priority_score.desc())
            .all()
        )

    def mark_resolved(
        self,
        recommendation_id: str,
        session: Session | None = None,
        *, dataset_id: str | None = None,
    ) -> DatasetRecommendation:
        """Mark a specific recommendation as resolved."""
        sess = self._resolve_session(session)
        query = (
            sess.query(DatasetRecommendation)
            .filter(DatasetRecommendation.recommendation_id == recommendation_id)
        )
        if dataset_id is not None:
            query = query.filter(DatasetRecommendation.dataset_id == dataset_id)
        recommendation = query.first()
        if not recommendation:
            raise ValueError(f"Recommendation {recommendation_id} not found")

        try:
            recommendation.status = "resolved"
            recommendation.resolved_at = datetime.now(UTC)
            sess.commit()
            sess.refresh(recommendation)
            logger.info("Resolved recommendation %s", recommendation_id)
            return recommendation
        except Exception as e:
            sess.rollback()
            raise ValueError(f"Failed to resolve recommendation: {e}") from e

    def delete_by_dataset_and_version(
        self,
        dataset_id: str,
        version_id: str,
        session: Session | None = None,
    ) -> int:
        """Delete recommendations for a specific dataset version."""
        sess = self._resolve_session(session)
        try:
            count = (
                sess.query(DatasetRecommendation)
                .filter(
                    DatasetRecommendation.dataset_id == dataset_id,
                    DatasetRecommendation.version_id == version_id,
                )
                .delete()
            )
            sess.commit()
            logger.info(
                "Deleted %d recommendations for dataset %s, version %s",
                count,
                dataset_id,
                version_id,
            )
            return count
        except Exception as e:
            sess.rollback()
            raise ValueError(f"Failed to delete recommendations: {e}") from e


def get_dataset_recommendation_repository(
    db: Session = Depends(get_db_session),
) -> DatasetRecommendationRepository:
    """FastAPI dependency yielding a configured DatasetRecommendationRepository."""
    return DatasetRecommendationRepository(db=db)
