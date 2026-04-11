# 安全视角 — Security Perspective

## Evaluation Criteria

### Secrets Management
- No hardcoded passwords, API keys, tokens, or secrets in code
- Use environment variables or secret managers
- Secrets are not logged or exposed in error messages

### Injection Prevention
- SQL queries use parameterized statements
- No string concatenation in queries
- User input is validated and sanitized

### Authentication & Authorization
- Authentication is enforced on all protected endpoints
- Authorization checks are present and correct
- Session management follows security best practices

### Data Protection
- Sensitive data is encrypted at rest and in transit
- TLS/HTTPS is used for all external communication
- No sensitive data in URLs or logs

### Dependency Security
- No known CVEs in dependencies
- Dependencies are pinned and audited
