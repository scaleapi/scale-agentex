# Local development (OSS contributors)

Agentex local dev uses **public** Docker Hub base images by default. The `agentex/Dockerfile`
accepts an optional `DOCKER_REGISTRY` build arg — leave it **unset** for open-source onboarding.

## Quick preflight

Before `./dev.sh` or `make dev`:

```bash
python scripts/agentex_dev_doctor.py
```

Checks: `docker`, `uv`, daemon reachable, `agentex/docker-compose.yml` present, critical ports
free, and `DOCKER_REGISTRY` not pointing at private ECR ([#163](https://github.com/scaleapi/scale-agentex/issues/163)).

## Common failures

| Symptom | Fix |
|---------|-----|
| `401 Unauthorized` pulling `*.amazonaws.com` base image | `unset DOCKER_REGISTRY` and rebuild |
| Redis port conflict on `6379` | `brew services stop redis` (macOS) |
| Postgres port conflict on `5432` | Stop local Postgres or change host mapping |
| Docker not running | Start Docker Desktop |

## Start stack

```bash
./dev.sh          # macOS/Linux orchestration
# or
cd agentex && make dev
```

The compose file builds `agentex/Dockerfile` target `dev` without a private registry prefix.
