"""采集器公共协议。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar


SnapshotT = TypeVar("SnapshotT")


class BaseCollector(ABC, Generic[SnapshotT]):
    """所有采集器的最小接口。

    单个采集器失败时必须返回离线状态或抛出可隔离异常，不能阻塞其他数据源。
    """

    @abstractmethod
    async def collect(self) -> SnapshotT:
        """采集并返回一个不可依赖外部共享状态的快照。"""

