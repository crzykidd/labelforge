# Contributing

## Branches

**main** is always deployable. Merges require a pull request; CI must pass; direct push is blocked.

**dev** is the working branch. Push directly or open a PR — CI runs on every push. This is where day-to-day work lands. **Default: work on dev.**

**feature/\<name\>** branches are ad-hoc. Use one when a change is large or risky enough to warrant isolation from dev. Branch off dev, PR back to dev. Reach for one when it helps; there is no standing rule.

## Commits

Imperative present tense — "Add template recall endpoint", not "Added" or "Adds". No conventional-commits prefixes. One logical change per commit when practical; squash-merge from PRs when not. LF line endings enforced by `.gitattributes`.

## Release flow

Work lands in dev. CI builds and pushes the `dev` image on every push. When dev is ready to ship, open a PR from dev to main and merge it. Merging to main publishes `latest` and `main-<sha>`.

To mark a release, tag the merge commit on main:

```
git tag v1.2.3
git push origin v1.2.3
```

Pushing a `v*` tag triggers a build that publishes `vX.Y.Z`, `vX.Y`, `vX`, and re-tags `latest`. The first `v*` tag is when the first deployable slice ships — design-only commits do not get a release tag.

## CI

Every push to main or dev and every PR targeting either branch runs:

- **ruff check** and **ruff format --check** — Python linting and formatting
- **mypy** — Python type checking
- **pytest** — Python test suite
- **eslint** — TypeScript/JavaScript linting (if configured)
- **tsc --noEmit** — TypeScript type check
- **vite build** — frontend production build
- **docker build** — build verification, no push
- **CodeQL** — static analysis; also runs on Mondays 06:00 UTC via schedule

All jobs gate on file presence (`pyproject.toml`, `frontend/package.json`, `Dockerfile`) so workflows are harmless until the relevant code lands.

## Image registry

Images publish to `ghcr.io/crzykidd/labelforge`.

| Tag | When published | Retention |
|-----|----------------|-----------|
| `dev` | Push to dev | Always (rolling) |
| `dev-<sha>` | Push to dev | Last 10 |
| `latest` | Push to main; on v* tag | Always (rolling) |
| `main-<sha>` | Push to main | Last 10 |
| `vX.Y.Z`, `vX.Y`, `vX` | v* git tag | Forever |

Cleanup runs Sundays 04:00 UTC.

## Running CI locally

**Backend:**
```bash
ruff check .
ruff format --check .
mypy backend
pytest -q
```

**Frontend:**
```bash
cd frontend
npm run lint
npx tsc --noEmit
npm run build
```

**Docker:**
```bash
docker build .
```

## Where things live

- [`CLAUDE.md`](../CLAUDE.md) — coding session context, stack constraints, working style
- [`docs/PRD.md`](PRD.md) — scope and success criteria
- [`docs/features/`](features/) — per-feature designs
- [`docs/decisions.md`](decisions.md) — architecture decision log; read before contradicting a locked decision
- [`CHANGELOG.md`](../CHANGELOG.md) — user-visible change history
