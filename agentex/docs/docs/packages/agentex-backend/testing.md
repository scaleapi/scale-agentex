## Backend: testing (`agentex/tests/`)

The backend test suite is organized into unit and integration tests, with shared fixtures to reduce setup overhead.

### Test types

- **Unit tests**: `tests/unit/`
  - Fast, isolated, heavy use of mocks/fakes.
  - Focus on domain logic (use cases, services), repository interface behavior, and utility functions.
- **Integration tests**: `tests/integration/`
  - Exercise the HTTP API and real infrastructure dependencies.
  - Use testcontainers to spin up Postgres/Redis/Mongo as needed.

### Fixtures

- `tests/fixtures/`: common fixtures (containers, databases, repositories, services).
- `tests/integration/fixtures/`: integration-specific fixtures (test client, environment helpers).

### Running tests

From `agentex/`:

```bash
make test
make test-unit
make test-integration
```

To run a single file or a subset, use `FILE=` or `NAME=`:

```bash
make test FILE=tests/unit/test_foo.py
make test NAME=crud
```

