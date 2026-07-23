"""Narrative Entity / Alias service (Agent D).

Implements ``NarrativeEntityService`` Protocol plus get/list/archive/supersede
and Alias lock/list helpers required by Phase 1B Entity Contract.

Rules:
- Entity id is stable identity; no auto-merge by name.
- Alias never overwrites canonical_name.
- Entity lock is orthogonal to Alias review_status.
- archived / superseded are soft lifecycle states (not physical delete).
- Formal alias lookup is book-scoped and returns ambiguity — never silent pick.
- merge_entities is unsupported until Schema gains superseded_by_entity_id.
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

    def supersede_entity(self, entity_id: int) -> NarrativeEntity:
        """Mark identity superseded (soft).

        Schema has no ``superseded_by_entity_id`` — target link is not recorded.
        See Integration Issue II-ENTITY-001 / merge boundary doc.
        """
        entity = self.get_entity(entity_id)
        if entity.lifecycle_status == EntityLifecycleStatus.SUPERSEDED:
            return entity  # idempotent
        if entity.lifecycle_status == EntityLifecycleStatus.ARCHIVED:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ENTITY_NOT_ACTIVE,
                f"cannot supersede archived entity: {entity_id}",
            )
        entity.lifecycle_status = EntityLifecycleStatus.SUPERSEDED
        return self._repo.save_entity(entity)

    def merge_entities(self, survivor_id: int, absorbed_id: int) -> Any:
        """Frozen semantic only — Schema cannot record superseded target.

        ``narrative_entities`` has no ``superseded_by_entity_id`` (unlike Asset /
        Relation). Without that column, a safe merge that preserves target
        lineage cannot be implemented without altering ``models.py``.
        """
        # Validate inputs exist so callers get ENTITY_NOT_FOUND vs unsupported.
        if int(survivor_id) == int(absorbed_id):
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ENTITY_MERGE_NOT_SUPPORTED,
                "merge_entities: source and target must differ; "
                "full merge unsupported without superseded_by_entity_id",
            )
        survivor = self.get_entity(survivor_id)
        absorbed = self.get_entity(absorbed_id)
        if survivor.book_id != absorbed.book_id:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ENTITY_MERGE_NOT_SUPPORTED,
                "merge_entities: entities must belong to the same book; "
                "full merge unsupported without superseded_by_entity_id",
            )
        raise NarrativeCoreError(
            NarrativeCoreErrorCode.ENTITY_MERGE_NOT_SUPPORTED,
            "merge_entities is not supported in Phase 1B Agent D: "
            "narrative_entities lacks superseded_by_entity_id; "
            "refusing to mutate aliases or lifecycle without target lineage. "
            "See II-ENTITY-001.",
        )

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
