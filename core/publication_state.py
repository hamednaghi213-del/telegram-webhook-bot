"""Publication delivery state abstraction.

The production implementation is intentionally in-memory until an additive
database migration is approved.  The publication engine depends only on this
interface so a durable Supabase implementation can replace it later.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import threading
from typing import Dict, Optional, Set, Tuple


@dataclass
class DeliveryState:
    source_key: str
    target_identity: str
    attempt: int = 0
    status: str = "pending"
    completed_parts: Set[str] = field(default_factory=set)
    message_ids: Dict[str, int] = field(default_factory=dict)
    message_chat_ids: Dict[str, str] = field(default_factory=dict)
    error: Optional[str] = None


class PublicationStateStore(ABC):
    @abstractmethod
    def claim_source(self, source_key: str) -> bool: ...

    @abstractmethod
    def claim_destination(self, source_key: str, target_identity: str) -> DeliveryState: ...

    @abstractmethod
    def begin_attempt(self, source_key: str, target_identity: str) -> Optional[DeliveryState]: ...

    @abstractmethod
    def part_succeeded(self, source_key: str, target_identity: str, part: str,
                       message_id: Optional[int] = None,
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
        self._sources: Set[str] = set()
        self._deliveries: Dict[Tuple[str, str], DeliveryState] = {}

    def claim_source(self, source_key: str) -> bool:
        with self._lock:
            first = source_key not in self._sources
            self._sources.add(source_key)
            return first

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
            state.attempt += 1
            state.status = "sending"
            state.error = None
            return state

    def part_succeeded(self, source_key: str, target_identity: str, part: str,
                       message_id: Optional[int] = None,
                       destination_chat_id: Optional[str] = None) -> None:
        with self._lock:
            state = self.claim_destination(source_key, target_identity)
            state.completed_parts.add(part)
            if message_id is not None:
                state.message_ids[part] = int(message_id)
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


DEFAULT_PUBLICATION_STATE_STORE = InMemoryPublicationStateStore()
