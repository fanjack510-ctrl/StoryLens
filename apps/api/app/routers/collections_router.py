"""书单的读写口。

书单免费：它不调用模型，是个文件夹。付费的是在一组书上做的事（共性视图、跨书检索），
那些各自把自己的门——所以这个文件里一道 Pro 门都没有，那是故意的。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.collection_service import (
    NAME_MAX,
    CollectionError,
    add_books,
    create_collection,
    delete_collection,
    list_collections,
    read_collection,
    remove_book,
    update_collection,
)

router = APIRouter(prefix="/api/v1", tags=["collections"])


def _fail(exc: CollectionError) -> None:
    status = 404 if exc.code.endswith("NOT_FOUND") else 400
    raise HTTPException(status_code=status, detail={"error_code": exc.code, "message": exc.message})


class CreateCollectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=NAME_MAX)
    #: 建这个书单是为了看什么。几周后回来时，这句话是唯一能说明当初为什么圈这批书的东西。
    note: str = Field(default="", max_length=2000)


class UpdateCollectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=NAME_MAX)
    note: str | None = Field(default=None, max_length=2000)


class AddBooksRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    book_ids: list[int] = Field(min_length=1)


@router.get("/collections")
def get_collections(db: Session = Depends(get_db)) -> dict:
    return {"items": list_collections(db)}


@router.post("/collections")
def post_collection(body: CreateCollectionRequest, db: Session = Depends(get_db)) -> dict:
    try:
        result = create_collection(db, name=body.name, note=body.note)
        db.commit()
    except CollectionError as exc:
        db.rollback()
        _fail(exc)
        raise
    return result


@router.get("/collections/{collection_id}")
def get_collection(collection_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        return read_collection(db, collection_id)
    except CollectionError as exc:
        _fail(exc)
        raise


@router.patch("/collections/{collection_id}")
def patch_collection(
    collection_id: int, body: UpdateCollectionRequest, db: Session = Depends(get_db)
) -> dict:
    try:
        result = update_collection(db, collection_id, name=body.name, note=body.note)
        db.commit()
    except CollectionError as exc:
        db.rollback()
        _fail(exc)
        raise
    return result


@router.delete("/collections/{collection_id}")
def del_collection(collection_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        delete_collection(db, collection_id)
        db.commit()
    except CollectionError as exc:
        db.rollback()
        _fail(exc)
        raise
    return {"deleted": True}


@router.post("/collections/{collection_id}/books")
def post_books(
    collection_id: int, body: AddBooksRequest, db: Session = Depends(get_db)
) -> dict:
    try:
        result = add_books(db, collection_id, [int(b) for b in body.book_ids])
        db.commit()
    except CollectionError as exc:
        db.rollback()
        _fail(exc)
        raise
    return result


@router.delete("/collections/{collection_id}/books/{book_id}")
def del_book(collection_id: int, book_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        result = remove_book(db, collection_id, book_id)
        db.commit()
    except CollectionError as exc:
        db.rollback()
        _fail(exc)
        raise
    return result
