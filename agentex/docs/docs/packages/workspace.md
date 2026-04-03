## Repository workspace

This repository is a multi-package workspace:

- **Python workspace (root `pyproject.toml`)**: defines shared tooling and points at the backend package as a workspace member.
- **Backend Python package (`agentex/pyproject.toml`)**: the FastAPI + Temporal server.
- **Frontend Node package (`agentex-ui/package.json`)**: the Next.js UI.

### Python workspace (`/pyproject.toml`)

The root `pyproject.toml` exists primarily to:

- declare top-level dev tooling (ruff, pre-commit, etc.)
- define the uv workspace membership (`agentex/`)

### Backend package (`agentex/`)

The backend is a standard Python project managed via uv and hatchling, with grouped dependencies for:

- development (`--group dev`)
- testing (`--group test`)
- docs (`--group docs`)

### Frontend package (`agentex-ui/`)

The UI is a standard npm package with scripts for:

- development (`npm run dev`)
- type checking (`npm run typecheck`)
- linting (`npm run lint`)
- testing (`npm test`)

### CI and quality gates

CI is defined under `.github/workflows/` and includes separate checks for backend and UI (lint/typecheck/tests). When adding new code, prefer:

- keeping backend logic covered with unit tests
- keeping frontend utilities covered with `vitest`

