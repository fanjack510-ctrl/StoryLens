"""素材库的表。与 models.py 分文件、共用同一个 Base——models.py 已经 52 张表，
是并行开发的冲突热点，素材库的表全部住在这里（迁移编号 20260823_025_material_lab）。

设计要点（对应交接说明第三节的坑）：**不复用 StoryLens 的 Scene 表**。那张表绑在
created_by_run_id 上，是分析产物；素材库的"场景"是解析产物（textseg 对章节文本的
确定性切分），所以这里的行直接挂 chapter_id + 章内偏移，场景只是行上的一组字段
（scene_seq / char_start / char_end），不是一张表。

与源项目 31 张表的对应：books/platforms/genres/收藏/导出等都用 StoryLens 已有的
概念顶替；真正搬过来的只有 5 张——原子、资料、模式簇、证据、任务。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import Base, utc_now


class MaterialLabRun(Base):
    """一次"对一本书跑本地素材引擎"的任务记录。

    引擎是确定性的、不花钱（provider='local'），所以没有 token/cost 字段；
    记录存在的意义是让重跑可见：什么时候跑的、用的哪个类型模板、产出了多少。
    """

    __tablename__ = "material_lab_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(
        ForeignKey("books.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="running")
    #: material-lab 自己的 10 类型体系之一（xuanyi/xuanhuan/...），与作品画像五轴无关。
    genre_slug: Mapped[str] = mapped_column(String(32), default="")
    #: user = 用户指定；auto = guess_genre 猜的（置信度见 genre_confidence）。
    genre_source: Mapped[str] = mapped_column(String(16), default="auto")
    genre_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    chapter_count: Mapped[int] = mapped_column(Integer, default=0)
    scene_count: Mapped[int] = mapped_column(Integer, default=0)
    material_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_chapters: Mapped[int] = mapped_column(Integer, default=0)
    skipped_short_scenes: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class MaterialLabPattern(Base):
    """模式簇：把"钥匙/戒指/门禁卡"折叠成"人物持有不属于自己的私人物件"之后的那个抽象。

    同 (genre_slug, signature) 精确命中即同簇；否则在同 (genre_slug, category_key)
    内按 dedup.similarity ≥ 0.62 归并——阈值与源项目 DEFAULTS 一致，在 service 里。
    """

    __tablename__ = "material_lab_patterns"

    id: Mapped[int] = mapped_column(primary_key=True)
    genre_slug: Mapped[str] = mapped_column(String(32))
    category_key: Mapped[str] = mapped_column(String(64))
    core_pattern: Mapped[str] = mapped_column(String(500))
    mechanism: Mapped[str] = mapped_column(String(200), default="")
    #: dedup.signature(core_pattern) —— 归一化后 sha1 前 16 位。
    signature: Mapped[str] = mapped_column(String(16))
    variant_count: Mapped[int] = mapped_column(Integer, default=0)
    book_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    __table_args__ = (
        Index("ix_material_lab_patterns_genre_signature", "genre_slug", "signature"),
        Index("ix_material_lab_patterns_genre_category", "genre_slug", "category_key"),
    )


class MaterialLabAtom(Base):
    """Story Atom：九类事实抽取的中间产物。char_pos 是章内偏移。"""

    __tablename__ = "material_lab_atoms"

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(
        ForeignKey("books.id", ondelete="CASCADE"), index=True
    )
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[int] = mapped_column(
        ForeignKey("material_lab_runs.id", ondelete="CASCADE"), index=True
    )
    scene_seq: Mapped[int] = mapped_column(Integer, default=0)
    atom_type: Mapped[str] = mapped_column(String(16))
    value: Mapped[str] = mapped_column(String(200))
    norm_value: Mapped[str] = mapped_column(String(120))
    salience: Mapped[float] = mapped_column(Float, default=0.0)
    char_pos: Mapped[int] = mapped_column(Integer, default=0)
    meta_json: Mapped[str] = mapped_column(Text, default="{}")

    __table_args__ = (
        Index("ix_material_lab_atoms_book_chapter", "book_id", "chapter_id"),
    )


class MaterialLabEvidence(Base):
    """场景级溯源：这条资料是从哪一章哪一段文本里抽出来的。章内偏移。"""

    __tablename__ = "material_lab_evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(
        ForeignKey("books.id", ondelete="CASCADE"), index=True
    )
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[int] = mapped_column(
        ForeignKey("material_lab_runs.id", ondelete="CASCADE"), index=True
    )
    scene_seq: Mapped[int] = mapped_column(Integer, default=0)
    char_start: Mapped[int] = mapped_column(Integer, default=0)
    char_end: Mapped[int] = mapped_column(Integer, default=0)
    snippet: Mapped[str] = mapped_column(String(200), default="")
    note: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class MaterialLabMaterial(Base):
    """创作资料：标题 + 可发表示例 + corePattern 五件套 + 评分。

    concise_example 由槽位重组而来，从不拼接原文——这是引擎的核心承诺，
    也是这张表可以放心展示给用户的原因。
    """

    __tablename__ = "material_lab_materials"

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(
        ForeignKey("books.id", ondelete="CASCADE"), index=True
    )
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[int] = mapped_column(
        ForeignKey("material_lab_runs.id", ondelete="CASCADE"), index=True
    )
    pattern_id: Mapped[int | None] = mapped_column(
        ForeignKey("material_lab_patterns.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    evidence_id: Mapped[int | None] = mapped_column(
        ForeignKey("material_lab_evidence.id", ondelete="SET NULL"), nullable=True
    )
    scene_seq: Mapped[int] = mapped_column(Integer, default=0)
    char_start: Mapped[int] = mapped_column(Integer, default=0)
    char_end: Mapped[int] = mapped_column(Integer, default=0)
    place: Mapped[str] = mapped_column(String(32), default="")
    time_cue: Mapped[str] = mapped_column(String(64), default="")

    genre_slug: Mapped[str] = mapped_column(String(32), default="")
    material_type: Mapped[str] = mapped_column(String(16))
    category_key: Mapped[str] = mapped_column(String(64))
    subcategory_key: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(200))
    concise_example: Mapped[str] = mapped_column(Text)
    core_pattern: Mapped[str] = mapped_column(String(500))
    mechanism: Mapped[str] = mapped_column(String(200))
    suspense_question: Mapped[str] = mapped_column(String(500))
    applicable_stage: Mapped[str] = mapped_column(String(32), default="")
    applicable_scene: Mapped[str] = mapped_column(String(64), default="")
    emotion: Mapped[str] = mapped_column(String(32), default="")
    tags_json: Mapped[str] = mapped_column(Text, default="[]")
    signals_json: Mapped[str] = mapped_column(Text, default="{}")

    quality_score: Mapped[int] = mapped_column(Integer, default=0)
    score_json: Mapped[str] = mapped_column(Text, default="{}")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    pattern_similarity: Mapped[float] = mapped_column(Float, default=1.0)
    is_primary_variant: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    __table_args__ = (
        Index("ix_material_lab_materials_book_chapter", "book_id", "chapter_id"),
        Index("ix_material_lab_materials_type", "material_type"),
        Index("ix_material_lab_materials_category", "category_key"),
        Index("ix_material_lab_materials_score", "quality_score"),
    )


class MaterialLabLegacyImport(Base):
    """一次旧资料库迁移批次。

    源 SQLite 始终只读打开；批次记录文件指纹和数量，让同一份资料可安全重试，
    也让失败能够被定位而不是留下一个无法解释的半成品状态。
    """

    __tablename__ = "material_lab_legacy_imports"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    source_name: Mapped[str] = mapped_column(String(255), default="library.db")
    source_size: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="running", index=True)
    source_material_count: Mapped[int] = mapped_column(Integer, default=0)
    imported_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class MaterialLabLegacyMaterial(Base):
    """从旧项目派生层迁入的纯知识条目；不保存小说正文或长摘录。"""

    __tablename__ = "material_lab_legacy_materials"

    id: Mapped[int] = mapped_column(primary_key=True)
    import_id: Mapped[int] = mapped_column(
        ForeignKey("material_lab_legacy_imports.id", ondelete="CASCADE"), index=True
    )
    source_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    source_material_id: Mapped[str] = mapped_column(String(64))
    source_pattern_id: Mapped[str] = mapped_column(String(64), default="")
    source_book_id: Mapped[str] = mapped_column(String(64), default="")
    source_book_title: Mapped[str] = mapped_column(String(255), default="")
    source_scene_id: Mapped[str] = mapped_column(String(64), default="")
    source_evidence_ids_json: Mapped[str] = mapped_column(Text, default="[]")

    genre_slug: Mapped[str] = mapped_column(String(32), default="", index=True)
    genre_label: Mapped[str] = mapped_column(String(32), default="")
    material_type: Mapped[str] = mapped_column(String(16), index=True)
    category_key: Mapped[str] = mapped_column(String(64), index=True)
    category_label: Mapped[str] = mapped_column(String(64), default="")
    subcategory_key: Mapped[str] = mapped_column(String(64), default="")
    subcategory_label: Mapped[str] = mapped_column(String(64), default="")
    title: Mapped[str] = mapped_column(String(200))
    concise_example: Mapped[str] = mapped_column(Text)
    core_pattern: Mapped[str] = mapped_column(String(500))
    mechanism: Mapped[str] = mapped_column(String(200), default="")
    suspense_question: Mapped[str] = mapped_column(String(500), default="")
    applicable_stage: Mapped[str] = mapped_column(String(32), default="")
    applicable_scene: Mapped[str] = mapped_column(String(64), default="")
    emotion: Mapped[str] = mapped_column(String(32), default="")
    tags_json: Mapped[str] = mapped_column(Text, default="[]")
    quality_score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    score_json: Mapped[str] = mapped_column(Text, default="{}")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    is_primary_variant: Mapped[int] = mapped_column(Integer, default=1, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    __table_args__ = (
        UniqueConstraint(
            "source_fingerprint", "source_material_id",
            name="uq_material_lab_legacy_source_material",
        ),
        Index(
            "ix_material_lab_legacy_genre_category",
            "genre_slug", "category_key",
        ),
    )
