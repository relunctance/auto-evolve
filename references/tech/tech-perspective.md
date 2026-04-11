# 技术视角 — Tech Perspective

## Evaluation Criteria

### Code Quality
- No duplicate code blocks (DRY principle)
- Functions are short (<=50 lines)
- No magic numbers or hardcoded strings
- Naming is consistent and descriptive

### Security
- No hardcoded passwords/tokens/secrets in code
- No SQL/NoSQL injection risks (use parameterized queries)
- Authentication/authorization is properly implemented
- Input validation on all user inputs

### Performance
- No N+1 queries (lazy loading where appropriate)
- No large loops that block the event loop
- Async/await used for I/O-bound operations
- Large data sets are paginated

### Error Handling
- No bare except: clauses
- Errors are not silently swallowed
- Errors propagate correctly through call stack
- All exceptions have meaningful messages

### Testing
- Core logic has unit tests
- Tests are not just happy-path
- Test files are co-located with source files
