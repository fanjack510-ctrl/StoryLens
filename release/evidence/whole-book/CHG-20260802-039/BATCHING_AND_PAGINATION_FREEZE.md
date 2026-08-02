# BATCHING AND PAGINATION FREEZE

## Provider batching

```
max_chapters_per_batch = 8
```

- Long books → multiple provider units / attempts under same stage.  
- Resume skips completed chapter_orders.  
- Token/window strategy reuses Private context level 2.

## Product API pagination

```
PAGINATION：YES（cursor preferred）
default limit：50
max limit：200
```

UI：virtualized list recommended at ≥100 chapters；not a schema requirement.

## Aggregation display

UI may group consecutive identical `primary_function` for readability.  
Grouped view is **presentation-only**；API SoT remains per-chapter items.
