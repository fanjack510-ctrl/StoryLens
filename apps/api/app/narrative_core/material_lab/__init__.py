"""素材库引擎（自 novel-material-lab 整块搬入的纯逻辑层）。

lexicon / genre_templates / atoms / materials / textseg 五个模块是从
`novel-material-lab/backend/app` 原样复制的——不要在这里"顺手改进"它们：
它们的行为已经在源项目里被 40,967 条产出验证过，任何改动都会让
「搬过来的还是原来那个引擎」这个前提失效。StoryLens 侧的适配全部放在
bridge.py 里。

引擎模块零数据库依赖。唯一例外是 service.py——它是 StoryLens 侧的落库
适配层（对应源项目 pipeline/dedup 绑 db 的那半边，用 SQLAlchemy 重写），
不从本 __init__ 导出，路由直接 import。quality.py 里的
rescore_with_final_counts 绑源项目的 db 模块，调用会 ImportError——
它的重写版是 service.rescore_library。
"""

from .bridge import (
    BookMaterials,
    SceneMaterials,
    chapter_text_from_paragraphs,
    extract_book_materials,
    extract_chapter_materials,
    guess_genre,
)
from .materials import Draft

__all__ = [
    "BookMaterials",
    "Draft",
    "SceneMaterials",
    "chapter_text_from_paragraphs",
    "extract_book_materials",
    "extract_chapter_materials",
    "guess_genre",
]
