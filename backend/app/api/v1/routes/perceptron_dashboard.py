"""Authenticated observation only: no learner mutation endpoints."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from backend.app.core.security import get_current_user
from backend.app.database.postgres import get_db_session
from backend.app.learning.dashboard import dashboard

router = APIRouter(prefix='/perceptron', tags=['Learning dashboard'])


@router.get('/dashboard')
def get_dashboard(response: Response, workspace_id: UUID,
                  days: int = Query(30, ge=1, le=90),
                  offset: int = Query(0, ge=0, le=10000),
                  limit: int = Query(25, ge=1, le=100),
                  db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    response.headers['Cache-Control'] = 'private, no-store'
    if db is None:
        raise HTTPException(503, 'Learning dashboard is temporarily unavailable')
    return dashboard(db.get_bind(), user.id, workspace_id, days, offset, limit)
