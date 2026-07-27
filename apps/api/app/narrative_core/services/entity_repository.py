"""Narrative Entity / Alias repository (Agent D).

Persistence helpers only; business rules live in ``entity_service``.
"""

from __future__ import annotations

from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import NarrativeEntity, NarrativeEntityAlias, utc_now
from app.narrative_core.asset_key import normalize_entity_name
from app.narrative_core.enums import (
    AliasReviewStatus,
    AliasType,
    EntityLifecycleStatus,
)


def normalize_alias_text(text: str) -> str:
    """Unified alias / canonical name normalization (frozen helper).

    Preserves distinctive CJK characters and digits. Does not convert
    simplified/traditional Chinese or invent nicknames.
    """
    return normalize_entity_name(text)


class NarrativeEntityRepository:
    """ORM access for ``narrative_entities`` / ``narrative_entity_aliases``."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_entity(
        self,
        book_id: int,
        *,
        entity_type: str,
        canonical_name: str,
        normalized_name: str,
        created_by: str | None = None,
        lifecycle_status: str = EntityLifecycleStatus.ACTIVE,
        is_locked: bool = False,
        locked_at: datetime | None = None,
    ) -> NarrativeEntity:
        entity = NarrativeEntity(
            book_id=int(book_id),
            entity_type=str(entity_type),
            canonical_name=str(canonical_name),
            normalized_name=str(normalized_name),
            lifecycle_status=str(lifecycle_status),
            is_locked=bool(is_locked),
            locked_at=locked_at,
            created_by=created_by,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        self._session.add(entity)
        self._session.flush()
        return entity

    def get_entity(self, entity_id: int) -> NarrativeEntity | None:
        return self._session.scalar(
            select(NarrativeEntity)
            .where(NarrativeEntity.id == int(entity_id))
            .options(selectinload(NarrativeEntity.aliases))
            .execution_options(populate_existing=True)
        )

    def list_entities(
        self,
        book_id: int,
        *,
        entity_type: str | None = None,
        lifecycle_status: str | None = None,
        include_inactive: bool = False,
    ) -> list[NarrativeEntity]:
        stmt = select(NarrativeEntity).where(NarrativeEntity.book_id == int(book_id))
        if entity_type is not None:
            stmt = stmt.where(NarrativeEntity.entity_type == str(entity_type))
        if lifecycle_status is not None:
            stmt = stmt.where(NarrativeEntity.lifecycle_status == str(lifecycle_status))
        elif not include_inactive:
            stmt = stmt.where(
                NarrativeEntity.lifecycle_status == EntityLifecycleStatus.ACTIVE
            )
        stmt = stmt.order_by(NarrativeEntity.id)
        return list(self._session.scalars(stmt))

    def save_entity(self, entity: NarrativeEntity) -> NarrativeEntity:
        entity.updated_at = utc_now()
        self._session.add(entity)
        self._session.flush()
        return entity

    def create_alias(
        self,
        entity_id: int,
        *,
        alias_text: str,
        normalized_alias: str,
        alias_type: str = AliasType.DISPLAY,
        source_run_id: int | None = None,
        source_snapshot_id: int | None = None,
        review_status: str = AliasReviewStatus.CANDIDATE,
        is_locked: bool = False,
    ) -> NarrativeEntityAlias:
        alias = NarrativeEntityAlias(
            entity_id=int(entity_id),
            alias_text=str(alias_text),
            normalized_alias=str(normalized_alias),
            alias_type=str(alias_type),
            source_run_id=source_run_id,
            source_snapshot_id=source_snapshot_id,
            review_status=str(review_status),
            is_locked=bool(is_locked),
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        self._session.add(alias)
        self._session.flush()
        return alias

    def get_alias(self, alias_id: int) -> NarrativeEntityAlias | None:
        return self._session.scalar(
            select(NarrativeEntityAlias)
            .where(NarrativeEntityAlias.id == int(alias_id))
            .options(selectinload(NarrativeEntityAlias.entity))
            .execution_options(populate_existing=True)
        )

    def find_alias_by_entity_normalized(
        self, entity_id: int, normalized_alias: str
    ) -> NarrativeEntityAlias | None:
        return self._session.scalar(
            select(NarrativeEntityAlias).where(
                NarrativeEntityAlias.entity_id == int(entity_id),
                NarrativeEntityAlias.normalized_alias == str(normalized_alias),
            )
        )

    def list_entity_aliases(self, entity_id: int) -> list[NarrativeEntityAlias]:
        return list(
            self._session.scalars(
                select(NarrativeEntityAlias)
                .where(NarrativeEntityAlias.entity_id == int(entity_id))
                .order_by(NarrativeEntityAlias.id)
            )
        )

    def save_alias(self, alias: NarrativeEntityAlias) -> NarrativeEntityAlias:
        alias.updated_at = utc_now()
        self._session.add(alias)
        self._session.flush()
        return alias

    def find_confirmed_alias_matches(
        self, book_id: int, normalized_alias: str
    ) -> list[NarrativeEntity]:
        """Formal lookup: confirmed aliases only, scoped to book_id."""
        stmt = (
            select(NarrativeEntity)
            .join(
                NarrativeEntityAlias,
                NarrativeEntityAlias.entity_id == NarrativeEntity.id,
            )
            .where(
                NarrativeEntity.book_id == int(book_id),
                NarrativeEntityAlias.normalized_alias == str(normalized_alias),
                NarrativeEntityAlias.review_status == AliasReviewStatus.CONFIRMED,
            )
            .options(selectinload(NarrativeEntity.aliases))
            .order_by(NarrativeEntity.id)
        )
        # Distinct entities if multiple confirmed alias rows somehow match.
        seen: set[int] = set()
        result: list[NarrativeEntity] = []
        for entity in self._session.scalars(stmt):
            if entity.id in seen:
                continue
            seen.add(entity.id)
            result.append(entity)
        return result

    def find_entities_by_normalized_name(
        self, book_id: int, normalized_name: str
    ) -> list[NarrativeEntity]:
        return list(
            self._session.scalars(
                select(NarrativeEntity)
                .where(
                    NarrativeEntity.book_id == int(book_id),
                    NarrativeEntity.normalized_name == str(normalized_name),
                )
                .order_by(NarrativeEntity.id)
            )
        )

    def delete_alias(self, alias: NarrativeEntityAlias) -> None:
        self._session.delete(alias)
        self._session.flush()

    def count_aliases_for_entity(self, entity_id: int) -> int:
        return len(self.list_entity_aliases(entity_id))
