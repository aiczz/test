"""图片解析不等待生图；完成的图片可公开缓存。"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.core.database import get_session
from app.core.dependencies import get_current_user_optional
from app.models.image_cache import ImageCache
from app.models.user import User
from app.services import image_service

router = APIRouter(prefix="/images", tags=["图片"])


class ImageRequest(BaseModel):
    kind: Literal["food", "recipe"]
    name: str = Field(min_length=1, max_length=160)


@router.post("/resolve")
def resolve_image(body: ImageRequest, session: Session = Depends(get_session),
                  user: User | None = Depends(get_current_user_optional)) -> dict:
    return image_service.resolve(session, body.kind, body.name, allow_generation=user is not None)


@router.get("/{key}")
def image_status(key: str, session: Session = Depends(get_session)) -> dict:
    row = session.get(ImageCache, key)
    if row is None:
        raise HTTPException(404, "图片尚未登记")
    return image_service.result(row)


@router.get("/{key}/content")
def image_content(key: str, session: Session = Depends(get_session)):
    row = session.get(ImageCache, key)
    if row is None or row.status != "ready":
        raise HTTPException(404, "图片尚未就绪")
    path = image_service.photo_path(row)
    if not path.is_file():
        raise HTTPException(404, "图片文件不可用")
    return FileResponse(path, headers={"Cache-Control": "public, max-age=86400",
                                       "X-Content-Type-Options": "nosniff"})
