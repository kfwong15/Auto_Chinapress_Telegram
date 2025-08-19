from dataclasses import dataclass
from typing import Optional, List

@dataclass
class Article:
    title: str
    url: str
    published_at: Optional[str]  # ISO 8601 string if available
    summary: Optional[str]
    images: List[str]
