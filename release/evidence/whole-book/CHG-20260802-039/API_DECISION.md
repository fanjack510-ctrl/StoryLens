# PRODUCT API FREEZE — WB-2.2

## Unique product result API

```
GET /api/v1/whole-book/runs/{run_id}/chapter-functions
```

## Pagination

```
PAGINATION REQUIRED：YES
```

Query（freeze）：

- `limit`（default 50，max 200）  
- `cursor`（opaque；preferred） **or** `offset` for v1 impl if cursor deferred — prefer cursor  
- Response includes `items`, `next_cursor`, `total_chapters`（if cheap）  

## Optional single-chapter

```
GET /api/v1/whole-book/runs/{run_id}/chapter-functions/{chapter_id}
```

Same V2 item envelope；404 if chapter not in result set（not “module absent”）.

## Envelope states

| result_status | Meaning |
|---|---|
| completed / available | V2 payload with chapters |
| insufficient | coverage_scope=insufficient；chapters=[] |
| failed | failure_code；no fake chapters |
| canceled | canceled；no completion UI |
| conflict | open conflict versions；confirmed preserved |
| absent | no result yet；**HTTP 404** mapped by UI to absent（not generic error） |

## Lab API（preserve）

```
GET /api/v1/whole-book-runs/{run_id}/results/chapter_functions
```

Lab may continue V1 adapter；Free product **must** use V2 product route.

## Prepare compatibility

```
GET /api/v1/books/{book_id}/whole-book/prepare
GET /api/v1/books/{book_id}/whole-book/free/prepare
```

**PRESERVED** — do not break.

## Evidence

Reuse existing Evidence Deep Link APIs；citations carry chapter_id + paragraph_index + offsets；**no fuzzy fallback**.
