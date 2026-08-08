# DeepSeek Architecture (CHG-20260808-060)

`
Whole-Book Pipeline
        |
ModelGateway
        |
Provider Adapter
   ├── aliyun_qwen_plus (preserved)
   └── deepseek (new)
`

Shared: overview / characters_events / structure / chapter_functions,
validation, repair, retry, evidence, materialize, project_result, Pause/Resume, Cost/Consent.

Only the Model Provider Adapter is swapped.
