# Changelog

All notable changes to this project are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-11-18

### Added

- `swift-app-bundler build`: release binary, Info.plist, translations, icon from a picture or a
  command, app extensions in PlugIns, signature with the hardened runtime; `--install` copies the
  app to ~/Applications.
- `swift-app-bundler release`: a signed disk image with the app, a link to Applications and extra
  folders, notarized with a Developer ID and a notary profile.
- `swift-app-bundler identity`: a self-signed identity in its own keychain, trusted for code
  signing, with its settings in local.mk.
- `swift-app-bundler.toml` for the app's name, product, parts and extensions.

[0.1.0]: https://github.com/Robertwlt03/swift-app-bundler/releases/tag/v0.1.0
