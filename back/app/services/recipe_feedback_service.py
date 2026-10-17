"""Explicit, reversible personal feedback; never infer allergies from dislikes."""
from fastapi import HTTPException
from sqlmodel import select
from app.models.recipe_feedback import RecipeFeedback
from app.repositories import recipe_repository
from app.utils.time import utcnow


def list_items(session, user_id):
    if user_id is None:
        return []
    return list(session.exec(select(RecipeFeedback).where(RecipeFeedback.user_id == user_id)).all())


def set_feedback(session, user_id, recipe_id, payload):
    if recipe_repository.get(session, recipe_id) is None:
        raise HTTPException(status_code=404, detail='菜谱不存在')
    row = session.exec(select(RecipeFeedback).where(
        RecipeFeedback.user_id == user_id, RecipeFeedback.recipe_id == recipe_id)).first()
    if payload.value == 'neutral':
        if row is not None:
            session.delete(row)
        session.commit()
        return {'recipe_id': recipe_id, 'value': 'neutral', 'reason': None}
    row = row or RecipeFeedback(user_id=user_id, recipe_id=recipe_id, rating=1)
    row.rating = 1 if payload.value == 'like' else -1
    row.reason = payload.reason if row.rating < 0 else None
    row.updated_at = utcnow()
    session.add(row)
    session.commit()
    return {'recipe_id': recipe_id, 'value': payload.value, 'reason': row.reason}
