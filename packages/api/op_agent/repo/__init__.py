"""資料層。

刻意抽象化：本地開發用 memory，上雲用 dynamodb，
之後要換成統一資訊的 Postgres 也只要再寫一個實作，agent 與 route 都不用改。
"""

from __future__ import annotations

from functools import lru_cache

from ..config import config
from .base import Repo


@lru_cache(maxsize=1)
def get_repo() -> Repo:
    """依 REPO_DRIVER 決定實作。Lambda 冷啟後重複使用同一個實例。"""
    if config.repo_driver == "dynamodb":
        from .dynamo import DynamoRepo

        return DynamoRepo()

    from .memory import MemoryRepo

    return MemoryRepo()


__all__ = ["Repo", "get_repo"]
