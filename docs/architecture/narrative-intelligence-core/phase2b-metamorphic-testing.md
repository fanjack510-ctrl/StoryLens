# Phase 2B Metamorphic Testing

Runner: `MetamorphicTestRunner`

## Transforms

1. Chapter title slight change  
2. Whitespace/newline change  
3. Renumber with same content  
4. Irrelevant preface  
5. Enhanced aux assets missing → degrade/partial  
6. Module execution order change  
7. Resume does not duplicate  
8. Output locale change keeps entity IDs  
9. Snapshot/context change rejects old checkpoint (via Checkpoint validator tests)  
10. Prompt Pack change rejects resume (via Checkpoint validator tests)

## Claim boundary

Does **not** claim Fake semantic stability.  
Validates identifiers, refs, hashes, schema, dedupe, and status stability only.
