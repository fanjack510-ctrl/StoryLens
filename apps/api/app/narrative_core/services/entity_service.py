"""Narrative Entity / Alias service (Agent D).

Implements ``NarrativeEntityService`` Protocol plus get/list/archive/supersede
and Alias lock/list helpers required by Phase 1B Entity Contract.

Rules:
- Entity id is stable identity; no auto-merge by name.
- Alias never overwrites canonical_name.
- Entity lock is orthogonal to Alias review_status.
- archived / superseded are soft lifecycle states (not physical delete).
- Formal alias lookup is book-scoped and returns ambiguity — never silent pick.
- merge_entities transfers aliases and records superseded_by_entity_id.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import NarrativeEntity, NarrativeEntityAlias, utc_now
from app.narrative_core.enums import (
    AliasReviewStatus,
    AliasType,
    EntityLifecycleStatus,
    EntityType,
)
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.services.entity_repository import (
    NarrativeEntityRepository,
    normalize_alias_text,
)

_ALIAS_REVIEW_RANK = {
    AliasReviewStatus.REJECTED: 0,
    AliasReviewStatus.CANDIDATE: 1,
    AliasReviewStatus.CONFIRMED: 2,
}


@dataclass(frozen=True)
class EntityMergeResult:
    """Auditable merge outcome — source superseded, target retains identity."""

    source: NarrativeEntity
    target: NarrativeEntity
    actor: str


@dataclass(frozen=True)
class AliasLookupResult:
    """Result of ``find_entity_by_alias`` — never silently picks among matches."""

    status: Literal["none", "unique", "ambiguous"]
    normalized_alias: str
    entities: tuple[NarrativeEntity, ...] = ()

    @property
    def entity(self) -> NarrativeEntity | None:
        if self.status == "unique" and len(self.entities) == 1:
            return self.entities[0]
        return None


class NarrativeEntityServiceImpl:
    """Implements Entity / Alias review + lock operations."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = NarrativeEntityRepository(session)

    # ------------------------------------------------------------------
    # Entity identity
    # ------------------------------------------------------------------

    def create_entity(
        self,
        book_id: int,
        *,
        entity_type: str,
        canonical_name: str,
        created_by: str | None = None,
    ) -> NarrativeEntity:
        name = (canonical_name or "").strip()
        if not name:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ENTITY_INVALID_NAME,
                "canonical_name must not be empty",
            )
        type_value = self._coerce_entity_type(entity_type)
        normalized = normalize_alias_text(name)
        if not normalized:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ENTITY_INVALID_NAME,
                "canonical_name normalizes to empty",
            )
        return self._repo.create_entity(
            int(book_id),
            entity_type=type_value,
            canonical_name=name,
            normalized_name=normalized,
            created_by=created_by,
        )

    def get_entity(self, entity_id: int) -> NarrativeEntity:
        entity = self._repo.get_entity(entity_id)
        if entity is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ENTITY_NOT_FOUND,
                f"entity not found: {entity_id}",
            )
        return entity

    def list_entities(
        self,
        book_id: int,
        *,
        entity_type: str | None = None,
        lifecycle_status: str | None = None,
        include_inactive: bool = False,
    ) -> list[NarrativeEntity]:
        return self._repo.list_entities(
            int(book_id),
            entity_type=entity_type,
            lifecycle_status=lifecycle_status,
            include_inactive=include_inactive,
        )

    def lock_entity(self, entity_id: int) -> NarrativeEntity:
        entity = self.get_entity(entity_id)
        if entity.is_locked:
            return entity  # idempotent
        entity.is_locked = True
        entity.locked_at = utc_now()
        return self._repo.save_entity(entity)

    def unlock_entity(self, entity_id: int) -> NarrativeEntity:
        entity = self.get_entity(entity_id)
        if not entity.is_locked:
            return entity  # idempotent
        entity.is_locked = False
        entity.locked_at = None
        return self._repo.save_entity(entity)

    def archive_entity(self, entity_id: int) -> NarrativeEntity:
        """Soft-archive. Does not physically delete; Alias rows retained."""
        entity = self.get_entity(entity_id)
        if entity.lifecycle_status == EntityLifecycleStatus.ARCHIVED:
            return entity  # idempotent
        if entity.lifecycle_status == EntityLifecycleStatus.SUPERSEDED:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ENTITY_NOT_ACTIVE,
                f"cannot archive superseded entity: {entity_id}",
            )
        entity.lifecycle_status = EntityLifecycleStatus.ARCHIVED
        return self._repo.save_entity(entity)

    def supersede_entity(
        self,
        entity_id: int,
        *,
        superseded_by_entity_id: int | None = None,
    ) -> NarrativeEntity:
        """Mark identity superseded (soft). Optionally record target lineage."""
        entity = self.get_entity(entity_id)
        if entity.lifecycle_status == EntityLifecycleStatus.SUPERSEDED:
            return entity  # idempotent
        if entity.lifecycle_status == EntityLifecycleStatus.ARCHIVED:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ENTITY_NOT_ACTIVE,
                f"cannot supersede archived entity: {entity_id}",
            )
        if superseded_by_entity_id is not None:
            target_id = int(superseded_by_entity_id)
            if target_id == entity.id:
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.ENTITY_MERGE_CONFLICT,
                    "entity cannot supersede itself",
                )
            target = self.get_entity(target_id)
            if target.book_id != entity.book_id:
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.ENTITY_MERGE_CONFLICT,
                    "supersede target must belong to the same book",
                )
            entity.superseded_by_entity_id = target.id
        entity.lifecycle_status = EntityLifecycleStatus.SUPERSEDED
        return self._repo.save_entity(entity)

    def merge_entities(
        self,
        source_entity_id: int,
        target_entity_id: int,
        *,
        actor: str = "user",
    ) -> EntityMergeResult:
        """Merge source into target: transfer aliases, supersede source."""
        source_id = int(source_entity_id)
        target_id = int(target_entity_id)
        if source_id == target_id:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ENTITY_MERGE_CONFLICT,
                "merge_entities: source and target must differ",
            )

        source = self.get_entity(source_id)
        target = self.get_entity(target_id)
        if source.book_id != target.book_id:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ENTITY_MERGE_CONFLICT,
                "merge_entities: entities must belong to the same book",
            )
        if target.lifecycle_status != EntityLifecycleStatus.ACTIVE:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ENTITY_NOT_ACTIVE,
                f"merge target must be active: {target_id}",
            )
        if source.lifecycle_status == EntityLifecycleStatus.SUPERSEDED:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ENTITY_MERGE_CONFLICT,
                f"source entity already superseded: {source_id}",
            )
        if source.lifecycle_status == EntityLifecycleStatus.ARCHIVED:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ENTITY_NOT_ACTIVE,
                f"cannot merge archived source entity: {source_id}",
            )

        try:
            with self._session.begin_nested():
                target_aliases = {
                    a.normalized_alias: a
                    for a in self._repo.list_entity_aliases(target.id)
                }
                for source_alias in list(self._repo.list_entity_aliases(source.id)):
                    existing = target_aliases.get(source_alias.normalized_alias)
                    if existing is None:
                        source_alias.entity_id = target.id
                        self._repo.save_alias(source_alias)
                        target_aliases[source_alias.normalized_alias] = source_alias
                    else:
                        self._merge_alias_rows(
                            source_alias=source_alias,
                            target_alias=existing,
                        )

                source.lifecycle_status = EntityLifecycleStatus.SUPERSEDED
                source.superseded_by_entity_id = target.id
                self._repo.save_entity(source)
                self._repo.save_entity(target)
        except NarrativeCoreError:
            raise
        except IntegrityError as exc:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ENTITY_MERGE_CONFLICT,
                f"merge_entities failed integrity check: {exc}",
            ) from exc

        return EntityMergeResult(source=source, target=target, actor=actor)

    # ------------------------------------------------------------------
    # Alias review
    # ------------------------------------------------------------------

    def add_alias_candidate(
        self,
        entity_id: int,
        *,
        alias_text: str,
        alias_type: str = AliasType.DISPLAY,
        source_run_id: int | None = None,
        source_snapshot_id: int | None = None,
    ) -> NarrativeEntityAlias:
        entity = self.get_entity(entity_id)
        if entity.lifecycle_status != EntityLifecycleStatus.ACTIVE:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ENTITY_NOT_ACTIVE,
                f"cannot add alias to inactive entity: {entity_id}",
            )
        raw = (alias_text or "").strip()
        if not raw:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ENTITY_INVALID_NAME,
                "alias_text must not be empty",
            )
        normalized = normalize_alias_text(raw)
        if not normalized:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ENTITY_INVALID_NAME,
                "alias_text normalizes to empty",
            )
        type_value = self._coerce_alias_type(alias_type)

        existing = self._repo.find_alias_by_entity_normalized(entity.id, normalized)
        if existing is not None:
            # Idempotent: same entity + normalized_alias returns existing row.
            return existing

        try:
            with self._session.begin_nested():
                return self._repo.create_alias(
                    entity.id,
                    alias_text=raw,
                    normalized_alias=normalized,
                    alias_type=type_value,
                    source_run_id=source_run_id,
                    source_snapshot_id=source_snapshot_id,
                    review_status=AliasReviewStatus.CANDIDATE,
                )
        except IntegrityError:
            # Concurrent insert of same (entity_id, normalized_alias).
            winner = self._repo.find_alias_by_entity_normalized(entity.id, normalized)
            if winner is not None:
                return winner
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ALIAS_DUPLICATE,
                f"duplicate normalized_alias under entity {entity.id}: {normalized}",
            )

    def confirm_alias(self, alias_id: int) -> NarrativeEntityAlias:
        alias = self._require_alias(alias_id)
        if alias.is_locked:
            if alias.review_status == AliasReviewStatus.CONFIRMED:
                return alias
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ALIAS_LOCKED,
                f"locked alias cannot change review_status: {alias_id}",
            )
        if alias.review_status == AliasReviewStatus.CONFIRMED:
            return alias  # idempotent
        alias.review_status = AliasReviewStatus.CONFIRMED
        return self._repo.save_alias(alias)

    def reject_alias(self, alias_id: int) -> NarrativeEntityAlias:
        alias = self._require_alias(alias_id)
        if alias.is_locked:
            if alias.review_status == AliasReviewStatus.REJECTED:
                return alias
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ALIAS_LOCKED,
                f"locked alias cannot change review_status: {alias_id}",
            )
        if alias.review_status == AliasReviewStatus.REJECTED:
            return alias  # idempotent
        alias.review_status = AliasReviewStatus.REJECTED
        return self._repo.save_alias(alias)

    def lock_alias(self, alias_id: int) -> NarrativeEntityAlias:
        alias = self._require_alias(alias_id)
        if alias.is_locked:
            return alias
        alias.is_locked = True
        return self._repo.save_alias(alias)

    def unlock_alias(self, alias_id: int) -> NarrativeEntityAlias:
        alias = self._require_alias(alias_id)
        if not alias.is_locked:
            return alias
        alias.is_locked = False
        return self._repo.save_alias(alias)

    def list_entity_aliases(self, entity_id: int) -> list[NarrativeEntityAlias]:
        self.get_entity(entity_id)  # ensure exists
        return self._repo.list_entity_aliases(entity_id)

    def find_entity_by_alias(
        self, book_id: int, alias_text: str
    ) -> AliasLookupResult:
        """Formal retrieval: confirmed aliases only, scoped to ``book_id``.

        Returns ``AliasLookupResult``:
        - none: no confirmed match
        - unique: exactly one entity
        - ambiguous: multiple entities share the confirmed alias

        Never silently selects the first match. rejected / candidate aliases
        do not participate.
        """
        normalized = normalize_alias_text(alias_text or "")
        if not normalized:
            return AliasLookupResult(status="none", normalized_alias=normalized)

        matches = self._repo.find_confirmed_alias_matches(int(book_id), normalized)
        if not matches:
            return AliasLookupResult(status="none", normalized_alias=normalized)
        if len(matches) == 1:
            return AliasLookupResult(
                status="unique",
                normalized_alias=normalized,
                entities=tuple(matches),
            )
        return AliasLookupResult(
            status="ambiguous",
            normalized_alias=normalized,
            entities=tuple(matches),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _require_alias(self, alias_id: int) -> NarrativeEntityAlias:
        alias = self._repo.get_alias(alias_id)
        if alias is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ALIAS_NOT_FOUND,
                f"alias not found: {alias_id}",
            )
        return alias

    def _coerce_entity_type(self, entity_type: str) -> str:
        value = (entity_type or "").strip()
        if not value:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ENTITY_INVALID_NAME,
                "entity_type must not be empty",
            )
        try:
            return EntityType(value).value
        except ValueError as exc:
            # Extensible Contract: allow unknown non-empty types that are not
            # book-specific free-form labels with whitespace/punctuation noise.
            # Reject obvious free text; require snake_case token.
            if not value.replace("_", "").isalnum() or " " in value:
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.ENTITY_INVALID_NAME,
                    f"entity_type not in frozen set and not extensible token: {value!r}",
                ) from exc
            return value

    def _coerce_alias_type(self, alias_type: str) -> str:
        value = (alias_type or AliasType.DISPLAY).strip() or AliasType.DISPLAY
        try:
            return AliasType(value).value
        except ValueError:
            return AliasType.OTHER.value

    @staticmethod
    def _alias_rank(review_status: str) -> int:
        try:
            status = AliasReviewStatus(review_status)
        except ValueError:
            return 0
        return _ALIAS_REVIEW_RANK.get(status, 0)

    def _merge_alias_rows(
        self,
        *,
        source_alias: NarrativeEntityAlias,
        target_alias: NarrativeEntityAlias,
    ) -> None:
        """Resolve duplicate normalized_alias during merge."""
        source_rank = self._alias_rank(source_alias.review_status)
        target_rank = self._alias_rank(target_alias.review_status)

        if source_rank > target_rank:
            winner, loser = source_alias, target_alias
            winner_on_target = False
        elif target_rank > source_rank:
            winner, loser = target_alias, source_alias
            winner_on_target = True
        elif source_alias.is_locked and not target_alias.is_locked:
            winner, loser = source_alias, target_alias
            winner_on_target = False
        elif target_alias.is_locked and not source_alias.is_locked:
            winner, loser = target_alias, source_alias
            winner_on_target = True
        elif source_alias.is_locked and target_alias.is_locked:
            if source_alias.review_status != target_alias.review_status:
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.ENTITY_MERGE_CONFLICT,
                    "locked aliases with conflicting review_status",
                )
            winner, loser = target_alias, source_alias
            winner_on_target = True
        else:
            winner, loser = target_alias, source_alias
            winner_on_target = True

        if winner is source_alias and not winner_on_target:
            if target_alias.is_locked and (
                target_alias.review_status != source_alias.review_status
                or not source_alias.is_locked
            ):
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.ENTITY_MERGE_CONFLICT,
                    "cannot downgrade or unlock locked target alias",
                )
            target_alias.alias_text = source_alias.alias_text
            target_alias.alias_type = source_alias.alias_type
            target_alias.review_status = source_alias.review_status
            target_alias.is_locked = source_alias.is_locked or target_alias.is_locked
            if source_alias.source_run_id is not None:
                target_alias.source_run_id = source_alias.source_run_id
            if source_alias.source_snapshot_id is not None:
                target_alias.source_snapshot_id = source_alias.source_snapshot_id
            self._repo.save_alias(target_alias)
            self._drop_losing_alias(loser, winner)
            return

        if not self._loser_may_be_dropped(loser, winner):
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ENTITY_MERGE_CONFLICT,
                "locked alias cannot be dropped without preserving status on winner",
            )
        self._drop_losing_alias(loser, winner)

    @staticmethod
    def _loser_may_be_dropped(
        loser: NarrativeEntityAlias,
        winner: NarrativeEntityAlias,
    ) -> bool:
        if not loser.is_locked:
            return True
        return (
            winner.is_locked
            and winner.review_status == loser.review_status
        )

    def _drop_losing_alias(
        self,
        loser: NarrativeEntityAlias,
        winner: NarrativeEntityAlias,
    ) -> None:
        if loser.id == winner.id:
            return
        self._repo.delete_alias(loser)
