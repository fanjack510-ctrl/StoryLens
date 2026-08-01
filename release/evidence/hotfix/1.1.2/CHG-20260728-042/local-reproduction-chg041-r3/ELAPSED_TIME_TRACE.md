# ELAPSED TIME TRACE — ~8 hours on Journey Run 2

## Timestamps (DB, Journey Run 2)

| Field | Value |
|-------|-------|
| created_at | `2026-07-28 15:05:07.189529` (naive) |
| started_at | `2026-07-28 15:05:07.191528` (naive) |
| updated_at | `2026-07-28 15:06:02.241914` (naive) |
| completed_at | `2026-07-28 15:05:36.172844` (naive) |
| failed_at | FIELD_NOT_PRESENT |

True wall duration ≈ **29–55 seconds**, not hours.

## Runtime context

| Item | Value |
|------|-------|
| Windows timezone | China Standard Time (UTC+08:00) |
| Freeze local time | `2026-07-28T23:16:39+08:00` |
| Server clock basis | UTC naive written by API `utc_now()` |

## Frontend path

| Step | Detail |
|------|--------|
| Function | `journeyElapsedMs` in `resolveCurrentReaderJourney.ts` |
| Parse | `Date.parse(started_at)` (**not** `parseAnalysisTimestamp`) |
| Display | `formatJourneyElapsed` → sidebar `elapsedOverride` on journey tab |

## Math

If naive `15:05:07` is **UTC** but `Date.parse` treats it as **local CST**:

- Parsed start = 15:05 China
- Viewer ≈ 23:16 China
- Elapsed ≈ **8.19 hours**

If parsed correctly as UTC:

- Start = 15:05 UTC = 23:05 China
- Elapsed ≈ **0.19 hours** (~11 minutes at freeze)

## Category

**A. UTC_AS_LOCAL** (naive UTC timestamp missing timezone suffix, parsed as local)

Also **C. MISSING_TIMEZONE_SUFFIX** as enabling condition.

Not old-run inheritance for this specific 8h figure: started_at belongs to Journey 2
and is only minutes before updated_at in DB.
