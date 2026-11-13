"""Data models for expression parsing and evaluation."""
from dataclasses import dataclass, field
from typing import List, Optional, Any


@dataclass
class Token:
    type: str
    value: str
    position: int = 0


@dataclass
class Node:
    kind: str
    value: Optional[str] = None
    children: List['Node'] = field(default_factory=list)


@dataclass
class ParseResult:
    ast: Optional[Node]
    tokens: List[Token] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0 and self.ast is not None
