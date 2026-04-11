# 可靠性视角 — Reliability Perspective

## Evaluation Criteria

### SLA Compliance
- Response time guarantees are met
- Availability targets are defined and tracked
- Error budgets are monitored

### Circuit Breakers
- External service calls are protected
- Circuit breaker patterns are implemented
- Fallback behavior is defined

### Retry & Timeout
- Retries have limits and backoff
- Timeouts are appropriate
- Idempotent operations are used for retries

### Graceful Degradation
- Core functionality works without optional services
- Feature flags enable quick rollbacks
- Health endpoints report true status
