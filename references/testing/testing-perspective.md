# 测试视角 — Testing Perspective

## Evaluation Criteria

### Test Coverage
- Core business logic has >80% coverage
- Critical paths are fully tested
- Edge cases and boundary conditions are covered

### Test Quality
- Tests are isolated and independent
- Tests are deterministic (no flakiness)
- Test names are descriptive
- Each test has a clear assertion

### Test Organization
- Unit tests co-located with source
- Integration tests in tests/ directory
- Test fixtures are reusable

### Missing Tests
- Untested modules are identified
- Smoke tests exist for critical flows
- Performance tests exist for hot paths
