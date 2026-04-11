# 可观测性视角 — Observability Perspective

## Evaluation Criteria

### Logging
- Structured logging (JSON format)
- Appropriate log levels (ERROR/WARN/INFO/DEBUG)
- No sensitive data in logs
- Log correlation IDs for tracing

### Metrics
- Business metrics are exposed
- System metrics (CPU, memory, latency) are tracked
- Custom metrics for key operations

### Tracing
- Request IDs propagated across services
- Latency breakdown per operation
- Trace sampling is configured

### Alerting
- Alerts are actionable (not alert fatigue)
- Alert thresholds are appropriately tuned
- On-call runbooks exist
