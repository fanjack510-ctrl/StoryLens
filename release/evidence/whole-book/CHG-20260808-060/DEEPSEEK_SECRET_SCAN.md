# Secret Scan

API Key must not appear in:
- Git (production code / evidence)
- Logs
- Evidence
- Provider request dumps
- UI (masked by default)

Independent keys: aliyun vs deepseek preserved on switch.

STATUS: ABSENT for production secrets.
Test fixtures use non-production TESTSECRET_* placeholders only.
