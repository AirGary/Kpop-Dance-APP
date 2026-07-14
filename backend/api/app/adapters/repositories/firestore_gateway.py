from collections.abc import Awaitable, Callable
from typing import Any, Protocol, TypeVar


Document = dict[str, Any]
T = TypeVar("T")


class FirestoreTransaction(Protocol):
    async def get(self, path: str) -> Document | None: ...

    def set(self, path: str, document: Document) -> None: ...

    def delete(self, path: str) -> None: ...


class FirestoreGateway(Protocol):
    async def run_transaction(
        self,
        operation: Callable[[FirestoreTransaction], Awaitable[T]],
    ) -> T: ...

    async def get(self, path: str) -> Document | None: ...

    async def query_less_than_or_equal(
        self,
        collection: str,
        field: str,
        value: object,
    ) -> list[Document]: ...


class GoogleFirestoreGateway:
    def __init__(self, project_id: str) -> None:
        from google.cloud import firestore_v1

        self._firestore = firestore_v1
        self._client = firestore_v1.AsyncClient(project=project_id)

    async def run_transaction(
        self,
        operation: Callable[[FirestoreTransaction], Awaitable[T]],
    ) -> T:
        transaction = self._client.transaction()

        @self._firestore.async_transactional
        async def execute(native_transaction):
            wrapper = _GoogleFirestoreTransaction(self._client, native_transaction)
            return await operation(wrapper)

        return await execute(transaction)

    async def get(self, path: str) -> Document | None:
        snapshot = await self._client.document(path).get()
        return snapshot.to_dict() if snapshot.exists else None

    async def query_less_than_or_equal(
        self,
        collection: str,
        field: str,
        value: object,
    ) -> list[Document]:
        from google.cloud.firestore_v1.base_query import FieldFilter

        query = self._client.collection(collection).where(
            filter=FieldFilter(field, "<=", value)
        )
        return [snapshot.to_dict() async for snapshot in query.stream()]


class _GoogleFirestoreTransaction:
    def __init__(self, client, transaction) -> None:
        self._client = client
        self._transaction = transaction

    async def get(self, path: str) -> Document | None:
        snapshot = await self._client.document(path).get(
            transaction=self._transaction
        )
        return snapshot.to_dict() if snapshot.exists else None

    def set(self, path: str, document: Document) -> None:
        self._transaction.set(self._client.document(path), document)

    def delete(self, path: str) -> None:
        self._transaction.delete(self._client.document(path))
