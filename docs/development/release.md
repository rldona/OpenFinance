# Prepare a release

Checklist for publishing an OpenFinance version. The first is **v0.1.0** (OF-504). Its tag is created once two conditions are met: one month of real use with your data and OF-108 finished (it already is).

A Vercel *preview* is never deployed: everything goes through GitHub and the normal merge flow.

## 1. Prerequisites

- [ ] All the version's tickets closed in [roadmap.md](../product/roadmap.md). For v0.1.0, also **OF-108** ("mi gasto" (my spending) view).
- [ ] For v0.1.0: **at least one month of real use** with your data, with no open issues affecting amounts or privacy.
- [ ] Branch `main` up to date and with no local changes (clean `git status`).

## 2. Licenses

- [ ] `make licenses CHECK=1` passes.
- [ ] If dependencies have changed since the last audit, regenerate the tables with `make licenses` and update [docs/legal/dependencias.md](../legal/dependencias.md) (including the date).
- [ ] [`LICENSE`](../../LICENSE) unchanged: it is the literal AGPL-3.0 text ([ADR-0008](../adr/0008-licencia-agpl.md)).

## 3. Version

Replace the development version (`0.1.0.dev0` in Python, `0.1.0-dev` in npm) with the release version, everywhere:

- [ ] `services/api/pyproject.toml` → `version = "0.1.0"`, and then `cd services/api && uv lock` so `uv.lock` picks up the version.
- [ ] `apps/web/package.json` → `"version": "0.1.0"`, and then `cd apps/web && npm install --package-lock-only` to update `package-lock.json` (two entries).
- [ ] `make openapi`: the `info.version` in `apps/web/openapi.json` comes from the package version, and CI fails if it is not up to date.
- [ ] Check that no development version remains: `git grep -nE '0\.1\.0[.-]dev' -- ':!docs/development/release.md'` returns nothing.

## 4. CHANGELOG

- [ ] In [CHANGELOG.md](../../CHANGELOG.md), rename `## [Unreleased]` to `## [0.1.0] - YYYY-MM-DD` with the tag date, remove "Pendiente antes de 0.1.0" (Pending before 0.1.0) and open an empty `## [Unreleased]` above it.
- [ ] Check that each item is understandable without knowing the code.

## 5. Checks

- [ ] `make check` passes locally (lint, types, tests and build).
- [ ] Pull request with the changes from steps 2 to 4, signed commits (`git commit -s`, see [CONTRIBUTING.md](../../CONTRIBUTING.md)) and **green CI**: `backend`, `frontend`, `licenses` and `compose-e2e` in both modes (`direct` and `https`).
- [ ] Merge to `main` and green CI on `main` too.
- [ ] Clean installation following [Install at home](../deployment/home.md) from `main`. Restore a real backup (`make restore`) and check that the balances match the bank's.

## 6. Tag and GitHub release

Only when everything above is checked:

```bash
git switch main && git pull --ff-only
git tag -a v0.1.0 -m "OpenFinance v0.1.0"
git push origin v0.1.0
awk '/^## \[0\.1\.0\]/{f=1;next} /^## \[/{f=0} f' CHANGELOG.md > release-notes.md
gh release create v0.1.0 --verify-tag --title "OpenFinance v0.1.0" --notes-file release-notes.md
rm release-notes.md
```

- [ ] **Annotated** tag `v0.1.0` on the `main` commit with green CI.
- [ ] GitHub release with the notes from the 0.1.0 section of the CHANGELOG.
- [ ] The `Release` workflow (`.github/workflows/release.yml`) runs on its own when the tag is pushed and publishes the `openfinance-api` and `openfinance-web` images to ghcr.io (amd64 and arm64), signed with cosign. Check that it finishes green and that `cosign verify` (see [Install at home](../deployment/home.md), "Imágenes publicadas" (Published images)) accepts both. Base images are pinned by digest: see the note about images in [dependencias.md](../legal/dependencias.md).

## 7. Afterwards

- [ ] Go back to a development version (`0.2.0.dev0` / `0.2.0-dev`), with `uv lock`, `npm install --package-lock-only` and `make openapi`.
- [ ] Mark OF-504 as done in [roadmap.md](../product/roadmap.md) and update the status in the README.
- [ ] Update the home installation to the tag following "8. Actualizar" (8. Upgrade) in [Install at home](../deployment/home.md).
