"""跨书检索：在所有分析过的书里找东西。"""

from app.narrative_core.cross_book.index import SearchItem, build_index
from app.narrative_core.cross_book.search import keyword_search

__all__ = ["SearchItem", "build_index", "keyword_search"]
