# swift-app-bundler: working notes for Claude

## Toolchain

- Python 3.13 or newer; the only dependency is console-look (pinned to a tag in `pyproject.toml`).
- macOS with Swift for everything it runs: swift, codesign, sips, iconutil, hdiutil, security.
- Lines at most 100 characters; every script opens with a head that says `Start:`.

## Commands

- Install for work: `pip install -e .`
- Tests, including a real build and disk image of `Tests/sample`: `python3 -m unittest discover -s Tests`
- All checks, as CI runs them: `check-pipeline` (check-pipeline.toml)

## Hard rules

- Nothing names an app: names, products, parts and extensions come from `swift-app-bundler.toml`.
- Never run `swift-app-bundler identity` on someone's Mac without being asked: it creates a
  keychain and asks for their password to trust a certificate.
- Every signature uses the hardened runtime (`--options runtime`); extensions are signed before
  the app, so the app's signature covers them.
- Passwords and identities never go into the repository; `local.mk` stays ignored.

## Where things go

- Settings: `src/swift_app_bundler/settings.py`
- Build and signing: `build.py`; disk image and notarization: `release.py`; identity: `identity.py`
- Command line: `__main__.py`; the sample app: `Tests/sample/`
- README pictures: `docs/pictures/` → `assets/pictures/` (markdown-graphics)

## Before every commit

Run `check-pipeline`; add a line to `CHANGELOG.md` under a new version for anything a user notices.

## Git

- English everywhere; commit messages follow Conventional Commits (`feat:`, `fix:`, `docs:` …).
- Work on a branch and merge into `main` through a pull request with green CI.
- A release is a tag `vX.Y.Z` that matches `pyproject.toml` and `CHANGELOG.md`.
