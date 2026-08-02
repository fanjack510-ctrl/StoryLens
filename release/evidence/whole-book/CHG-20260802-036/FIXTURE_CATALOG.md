# CHG-20260802-036 Fixture Catalog

Source of truth after seed: `%TEMP%\storylens-wb21-integration\MANUAL_FIXTURES.json`

| Entry key | book_id | run_id | structure_mode / state |
|---|---|---|---|
| structure_available | 1 | 1 | multi_stage |
| non_three_act | 2 | 2 | non_three_act |
| turning_points_empty | 3 | 3 | tp_empty |
| insufficient | 4 | 4 | insufficient |
| failed | 5 | 5 | failed_empty |
| canceled | 6 | 6 | cancelled run |
| conflict | 7 | 7 | confirmed + open conflict |
| evidence | 8 | 8 | multi_stage |
| structure_absent | 9 | — | snapshot only |
| cost_consent | 10 | — | prepare/consent |

Seed script: `apps/api/scripts_seed_wb21_integration.py`  
Banner / limitations include `FIXTURE_TEST_DATA`.
