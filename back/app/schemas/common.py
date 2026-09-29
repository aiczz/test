"""通用响应模型。

★ 全项目统一采用说明书 §28 的第二种方案：**标准 HTTP 状态码 + 直接返回 data**，
  不做 `{code, message, data}` 包装。认证接口已经这么做了，其余接口保持一致。
"""

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """分页响应（说明书 §30）。"""

    items: list[T]
    total: int
    page: int
    page_size: int
