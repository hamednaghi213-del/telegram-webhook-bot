"""Shared, transport-neutral content models for the publication pipeline."""

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Tuple
from uuid import uuid4


@dataclass(frozen=True)
class IncomingContentEnvelope:
    chat_id: int
    message_id: int
    update_id: Optional[int] = None
    media_group_id: Optional[str] = None
    text: str = ""
    entities: List[Dict[str, Any]] = field(default_factory=list)
    files: List[Dict[str, Any]] = field(default_factory=list)
    forward_source: Dict[str, Any] = field(default_factory=dict)

    @property
    def source_key(self) -> str:
        if self.media_group_id:
            return f"tg:{self.chat_id}:album:{self.media_group_id}"
        if self.update_id is not None:
            return f"tg:update:{self.update_id}"
        return f"tg:{self.chat_id}:message:{self.message_id}"


def deep_freeze(value: Any) -> Any:
    """Recursively detach and freeze values received from Telegram/DB payloads."""
    if isinstance(value, Mapping):
        return MappingProxyType({key: deep_freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(deep_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(deep_freeze(item) for item in value)
    return value


def _freeze_mapping(value: Optional[Mapping[str, Any]]) -> Mapping[str, Any]:
    return deep_freeze(dict(value or {}))


def _freeze_mapping_sequence(values) -> Tuple[Mapping[str, Any], ...]:
    return tuple(_freeze_mapping(value) for value in (values or ()))


@dataclass(frozen=True)
class PreparedContent:
    main_text: str = ""
    neutral_text: str = ""
    blockquote_blocks: Tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    expandable_blocks: Tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    other_entities: Tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    files: Tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    editorial_finalized: bool = False
    require_single_message: bool = False
    source_key: str = ""
    publication_id: str = field(default_factory=lambda: uuid4().hex)

    def __post_init__(self) -> None:
        object.__setattr__(self, "blockquote_blocks", _freeze_mapping_sequence(self.blockquote_blocks))
        object.__setattr__(self, "expandable_blocks", _freeze_mapping_sequence(self.expandable_blocks))
        object.__setattr__(self, "other_entities", _freeze_mapping_sequence(self.other_entities))
        object.__setattr__(self, "files", _freeze_mapping_sequence(self.files))

    @property
    def publication_identity(self) -> str:
        """Stable identity for this immutable instance and all of its retries."""
        return self.source_key or f"ephemeral:{self.publication_id}"


@dataclass(frozen=True)
class PublicationTarget:
    key: str
    kind: str
    platform: str
    external_id: str
    workspace_id: Optional[int] = None
    destination_id: Optional[int] = None
    destination: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "destination", _freeze_mapping(self.destination))


@dataclass(frozen=True)
class ExecutorResult:
    success: bool
    primary_message_id: Optional[int] = None
    message_ids: Tuple[int, ...] = field(default_factory=tuple)
    status_code: Optional[int] = None
    error: Optional[str] = None
    raw_result: Any = None
    error_code: Optional[int] = None
    operation: Optional[str] = None


@dataclass(frozen=True)
class DeliveryResult:
    platform: str
    workspace_id: Optional[int]
    destination_id: Optional[int]
    destination_chat_id: str
    primary_message_id: Optional[int] = None
    message_ids: Tuple[int, ...] = field(default_factory=tuple)
    blockquote_message_ids: Tuple[int, ...] = field(default_factory=tuple)
    followup_message_ids: Tuple[int, ...] = field(default_factory=tuple)
    status: str = "pending"
    error: Optional[str] = None
    status_code: Optional[int] = None
    error_code: Optional[int] = None
    failed_part: Optional[str] = None
    operation: Optional[str] = None
    attempt: int = 0
    idempotency_key: str = ""
