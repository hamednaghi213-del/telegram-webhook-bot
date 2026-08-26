"""Shared, transport-neutral content models for the publication pipeline."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


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


@dataclass
class PreparedContent:
    main_text: str = ""
    neutral_text: str = ""
    blockquote_blocks: List[Dict[str, Any]] = field(default_factory=list)
    expandable_blocks: List[Dict[str, Any]] = field(default_factory=list)
    other_entities: List[Dict[str, Any]] = field(default_factory=list)
    files: List[Dict[str, Any]] = field(default_factory=list)
    editorial_finalized: bool = False
    source_key: str = ""


@dataclass(frozen=True)
class PublicationTarget:
    key: str
    kind: str
    platform: str
    external_id: str
    workspace_id: Optional[int] = None
    destination_id: Optional[int] = None
    destination: Dict[str, Any] = field(default_factory=dict)
