# Phase 2B Language Contract

## source_language

`auto` | `zh` | `en` | `mixed` | `unknown`

## output_locale

`zh-CN` | `en-US`

## Rules

1. Source language and output locale are separate
2. Chinese source may yield English reports
3. English source may yield Chinese reports
4. Proper names/places must not be wrongly translated into new entities
5. Evidence Preview keeps original text
6. Analysis narrative follows `output_locale`
7. Module keys always stable English keys
8. No dual Chinese/English fact tables in the database
