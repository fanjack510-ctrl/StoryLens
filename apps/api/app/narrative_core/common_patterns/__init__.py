"""共性视图：把一组书摆在一起，看它们共同做对了什么。"""

from app.narrative_core.common_patterns.aggregate import BookFacts, collect_facts

__all__ = ["BookFacts", "collect_facts"]
