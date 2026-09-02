"""Publication delivery state abstraction.

The production implementation is intentionally in-memory until an additive
database migration is approved.  The publication engine depends only on this
interface so a durable Supabase implementation can replace it later.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import threading
from typing import Dict, Optional, Set, Tuple


SOURCE_STATUSES = {"pending", "sending", "partial", "succeeded", "failed", "failed_terminal"}
MAX_DELIVERY_ATTEMPTS = 5


@dataclass
class SourceState:
    source_key: str
    status: str = "pending"
    attempt: int = 0
    error: Optional[str] = None


@dataclass
class DeliveryState:
    source_key: str
    target_identity: str
    attempt: int = 0
    persistent_delivery_id: Optional[int] = None
    status: str = "pending"
    completed_parts: Set[str] = field(default_factory=set)
    message_ids: Dict[str, int] = field(default_factory=dict)
    all_message_ids: Dict[str, Tuple[int, ...]] = field(default_factory=dict)
    message_chat_ids: Dict[str, str] = field(default_factory=dict)
    error: Optional[str] = None


class PublicationStateStore(ABC):
    @abstractmethod
    def claim_source(self, source_key: str) -> bool: ...

    @abstractmethod
    def get_source(self, source_key: str) -> Optional[SourceState]: ...

    @abstractmethod
    def mark_source(self, source_key: str, status: str,
                    error: Optional[str] = None) -> None: ...

    @abstractmethod
    def claim_destination(self, source_key: str, target_identity: str) -> DeliveryState: ...

    @abstractmethod
    def begin_attempt(self, source_key: str, target_identity: str) -> Optional[DeliveryState]: ...

    @abstractmethod
    def part_succeeded(self, source_key: str, target_identity: str, part: str,
                       message_id: Optional[int] = None,
                       message_ids: Optional[Tuple[int, ...]] = None,
                       destination_chat_id: Optional[str] = None) -> None: ...

    @abstractmethod
    def part_completed(self, source_key: str, target_identity: str, part: str) -> bool: ...

    @abstractmethod
    def mark_succeeded(self, source_key: str, target_identity: str) -> None: ...

    @abstractmethod
    def mark_failed(self, source_key: str, target_identity: str, error: str) -> None: ...

    @abstractmethod
    def get_delivery(self, source_key: str, target_identity: str) -> Optional[DeliveryState]: ...

    @abstractmethod
    def successful_deliveries(self, source_key: str) -> Tuple[str, ...]: ...

    @abstractmethod
    def reset(self) -> None: ...


class InMemoryPublicationStateStore(PublicationStateStore):
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sources: Dict[str, SourceState] = {}
        self._deliveries: Dict[Tuple[str, str], DeliveryState] = {}

    def claim_source(self, source_key: str) -> bool:
        with self._lock:
            first = source_key not in self._sources
            if first:
                self._sources[source_key] = SourceState(source_key=source_key)
            return first

    def get_source(self, source_key: str) -> Optional[SourceState]:
        with self._lock:
            return self._sources.get(source_key)

    def mark_source(self, source_key: str, status: str,
                    error: Optional[str] = None) -> None:
        if status not in SOURCE_STATUSES:
            raise ValueError(f"invalid source status: {status}")
        with self._lock:
            self.claim_source(source_key)
            state = self._sources[source_key]
            if status == "sending" and state.status != "sending":
                state.attempt += 1
            state.status = status
            state.error = error

    def claim_destination(self, source_key: str, target_identity: str) -> DeliveryState:
        with self._lock:
            key = (source_key, target_identity)
            state = self._deliveries.get(key)
            if state is None:
                state = DeliveryState(source_key, target_identity)
                self._deliveries[key] = state
            return state

    def begin_attempt(self, source_key: str, target_identity: str) -> Optional[DeliveryState]:
        with self._lock:
            state = self.claim_destination(source_key, target_identity)
            # Atomic in-process lease. A concurrent webhook/timer may observe
            # the same source while the first request is between delivery
            # steps; it must not start a second external side effect.
            if state.status == "sending":
                return None
            if state.status == "failed_terminal" or (
                state.status == "failed" and state.attempt >= MAX_DELIVERY_ATTEMPTS
            ):
                state.status = "failed_terminal"
                return None
            state.attempt += 1
            state.status = "sending"
            state.error = None
            return state

    def part_succeeded(self, source_key: str, target_identity: str, part: str,
                       message_id: Optional[int] = None,
                       message_ids: Optional[Tuple[int, ...]] = None,
                       destination_chat_id: Optional[str] = None) -> None:
        with self._lock:
            state = self.claim_destination(source_key, target_identity)
            state.completed_parts.add(part)
            if message_id is not None:
                state.message_ids[part] = int(message_id)
            normalized_ids = tuple(
                int(value) for value in (message_ids or ())
                if isinstance(value, int) and not isinstance(value, bool)
            )
            if normalized_ids:
                state.all_message_ids[part] = normalized_ids
            if destination_chat_id is not None:
                state.message_chat_ids[part] = str(destination_chat_id)

    def part_completed(self, source_key: str, target_identity: str, part: str) -> bool:
        with self._lock:
            state = self._deliveries.get((source_key, target_identity))
            return bool(state and part in state.completed_parts)

    def mark_succeeded(self, source_key: str, target_identity: str) -> None:
        with self._lock:
            self.claim_destination(source_key, target_identity).status = "succeeded"

    def mark_failed(self, source_key: str, target_identity: str, error: str) -> None:
        with self._lock:
            state = self.claim_destination(source_key, target_identity)
            state.status = "failed"
            state.error = str(error)

    def get_delivery(self, source_key: str, target_identity: str) -> Optional[DeliveryState]:
        with self._lock:
            return self._deliveries.get((source_key, target_identity))

    def successful_deliveries(self, source_key: str) -> Tuple[str, ...]:
        with self._lock:
            return tuple(identity for (source, identity), state in self._deliveries.items()
                         if source == source_key and state.status == "succeeded")

    def reset(self) -> None:
        with self._lock:
            self._sources.clear()
            self._deliveries.clear()

class PersistentPublicationStateStore(
    InMemoryPublicationStateStore
):
    """
    Hybrid durable publication state.

    Atomic destination claims are persisted in Supabase.
    Existing in-memory behaviour remains available for the
    rest of the PublicationStateStore contract while durable
    part/status persistence is added incrementally.
    """

    def __init__(
        self,
        *,
        lease_owner: Optional[str] = None,
        lease_seconds: int = 120,
    ) -> None:
        super().__init__()

        self.lease_owner = (
            str(lease_owner)
            if lease_owner
            else None
        )

        self.lease_seconds = max(
            30,
            min(
                int(lease_seconds),
                900,
            ),
        )

    def begin_persistent_attempt(
        self,
        *,
        source_key: str,
        target_identity: str,
        platform: str,
        destination_chat_id: str = "",
        workspace_id: Optional[int] = None,
        destination_id: Optional[int] = None,
        delivery_generation: int = 1,
    ) -> Optional[DeliveryState]:
        """
        Atomically acquire the cross-worker delivery lease.

        This method is intentionally separate from
        begin_attempt() until the publication engine supplies
        the destination metadata required by the persistent
        claim RPC.
        """
        from core import database

        claim = (
            database
            .claim_persistent_publication_delivery(
                source_key=source_key,
                canonical_identity=target_identity,
                platform=platform,
                destination_chat_id=(
                    destination_chat_id
                ),
                workspace_id=workspace_id,
                destination_id=destination_id,
                delivery_generation=(
                    delivery_generation
                ),
                lease_owner=self.lease_owner,
                lease_seconds=self.lease_seconds,
            )
        )

        if not bool(claim.get("claimed")):
            return None

        state = self.claim_destination(
            source_key,
            target_identity,
        )

               state.attempt = int(
            claim.get("attempt_count") or 0
        )

        delivery_id = claim.get("delivery_id")
        state.persistent_delivery_id = (
            int(delivery_id)
            if delivery_id is not None
            else None
        )

        state.status = str(
            claim.get("status") or "sending"
        )
        state.error = None

        return state

DEFAULT_PUBLICATION_STATE_STORE = InMemoryPublicationStateStore()
