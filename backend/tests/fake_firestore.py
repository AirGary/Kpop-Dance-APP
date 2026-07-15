import asyncio
from collections.abc import Awaitable, Callable
from copy import deepcopy
from typing import Any, TypeVar


T = TypeVar("T")


class FakeTransaction:
    def __init__(self, documents: dict[str, dict[str, Any]]) -> None:
        self._documents = documents

    async def get(self, path: str) -> dict[str, Any] | None:
        document = self._documents.get(path)
        return deepcopy(document) if document is not None else None

    def set(self, path: str, document: dict[str, Any]) -> None:
        self._documents[path] = deepcopy(document)

    def delete(self, path: str) -> None:
        self._documents.pop(path, None)


class FakeFirestoreGateway:
    def __init__(self) -> None:
        self.documents: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def run_transaction(
        self,
        operation: Callable[[FakeTransaction], Awaitable[T]],
    ) -> T:
        async with self._lock:
            return await operation(FakeTransaction(self.documents))

    async def get(self, path: str) -> dict[str, Any] | None:
        document = self.documents.get(path)
        return deepcopy(document) if document is not None else None

    async def query_less_than_or_equal(
        self,
        collection: str,
        field: str,
        value: object,
    ) -> list[dict[str, Any]]:
        prefix = f"{collection}/"
        return [
            deepcopy(document)
            for path, document in self.documents.items()
            if path.startswith(prefix) and document[field] <= value
        ]

    async def query_equal(
        self,
        collection: str,
        field: str,
        value: object,
    ) -> list[dict[str, Any]]:
        prefix = f"{collection}/"
        return [
            deepcopy(document)
            for path, document in self.documents.items()
            if path.startswith(prefix) and document.get(field) == value
        ]
