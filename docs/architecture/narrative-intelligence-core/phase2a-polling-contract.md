# Phase 2A Polling Contract

## `MockRunPollingPolicy`

initial_interval_ms, running_interval_ms, paused_interval_ms, terminal_stop, max_consecutive_errors, backoff_policy

Defaults: running 1000–2000ms; paused/interrupted 3000–5000ms; terminal stop.

## Rules

No sub-1000ms polling; reduce when hidden; backoff on errors; stop on terminal; cancel old poll on run switch / app exit; discard stale by updated_at/version; network error ≠ run failed; frontend close ≠ cancel backend; no WebSocket.
