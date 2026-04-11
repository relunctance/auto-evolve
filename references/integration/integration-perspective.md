# 集成视角 — Integration Perspective

## Evaluation Criteria

### External API Integration
- API contracts are stable or versioned
- Retry logic with exponential backoff
- Timeout handling is appropriate

### Third-party SDK Integration
- SDK versions are pinned and auditable
- SDK features are fully utilized
- SDK quirks are documented

### Webhook Reliability
- Webhook signatures are verified
- Idempotent webhook handlers
- Webhook failures are logged and retried

### Message Queue Integration
- Queue consumers handle message failures
- Dead-letter queues are configured
- Message ordering is appropriate for use case
