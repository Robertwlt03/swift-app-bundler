"""Builds the disk image to share: the app, a link to the Applications folder and any folders the
settings add, such as an illustrated guide, in dist/<file>.dmg. The name has no version, so a
download link to the newest release (releases/latest/download/<file>.dmg) always works.

Start:  swift-app-bundler release
Needs:  macOS with Swift and a signing identity (SIGN_IDENTITY, which `swift-app-bundler
        identity` writes to local.mk).
        Free: the self-signed identity; users allow the disk image and the app once each
        ("Open Anyway"), because only a notarized image opens without asking.
        Paid: SIGN_IDENTITY="Developer ID Application: …" and NOTARY_PROFILE=<profile> also
        notarize the image, so macOS opens it without any warning.
[release] file (default: the name with hyphens), volume (default: the name) and extra, a table
of folders to add, such as extra = { Guide = "docs/guide" }.
"""

import shutil
from pathlib import Path

import console_look as console

from swift_app_bundler.build import StepFailed, build, run, shown, sign
from swift_app_bundler.settings import App

# MARK: Settings

RELEASE_FOLDER = "dist"
DEVELOPER_ID_PREFIX = "Developer ID Application:"


# MARK: Steps


def build_signed_app(app: App) -> Path:
    bundle = build(app, app.root / RELEASE_FOLDER / "app")
    run(["codesign", "--verify", "--strict", bundle])
    console.passed("Signature verified", shown(app, bundle))
    return bundle


def gather_contents(app: App, bundle: Path, contents: Path) -> None:
    """What the disk image shows: the app, the Applications link and the extra folders."""
    shutil.rmtree(contents, ignore_errors=True)
    shutil.copytree(bundle, contents / bundle.name, symlinks=True)
    (contents / "Applications").symlink_to("/Applications")
    for name, folder in app.release.get("extra", {}).items():
        shutil.copytree(app.root / folder, contents / name)
    console.passed("Gathered", ", ".join(["the app", "the Applications link",
                                          *app.release.get("extra", {})]))


def pack(app: App, contents: Path, disk_image: Path) -> None:
    # UDZO: a compressed, read-only image, the usual format for sharing apps.
    status = console.wait("Packing the disk image", [
        "hdiutil", "create", "-quiet", "-volname", app.release.get("volume", app.name),
        "-srcfolder", str(contents), "-format", "UDZO", "-ov", str(disk_image),
    ])
    shutil.rmtree(contents, ignore_errors=True)
    if status != 0:
        raise StepFailed("hdiutil", "the disk image could not be packed")
    sign(disk_image, app.signing())


def notarize_when_possible(disk_image: Path, signing: dict[str, str]) -> None:
    profile = signing.get("NOTARY_PROFILE", "")
    if not signing.get("SIGN_IDENTITY", "").startswith(DEVELOPER_ID_PREFIX) or not profile:
        return
    status = console.wait("Waiting for Apple to notarize the disk image", [
        "xcrun", "notarytool", "submit", str(disk_image), "--keychain-profile", profile, "--wait",
    ])
    if status != 0:
        raise StepFailed("notarytool", "Apple did not notarize the disk image")
    run(["xcrun", "stapler", "staple", disk_image])
    console.passed("Notarized", "macOS opens the app without a warning")


def release(app: App) -> Path:
    """The signed (and, when possible, notarized) disk image in dist/."""
    file_name = app.release.get("file", app.name.replace(" ", "-"))
    disk_image = app.root / RELEASE_FOLDER / f"{file_name}.dmg"
    missing = [folder for folder in app.release.get("extra", {}).values()
               if not (app.root / folder).is_dir()]
    if missing:  # before the build, so nothing is half done
        raise StepFailed("release", f"[release] extra names no folder {', '.join(missing)}")
    bundle = build_signed_app(app)
    contents = app.root / RELEASE_FOLDER / "contents"
    gather_contents(app, bundle, contents)
    pack(app, contents, disk_image)
    notarize_when_possible(disk_image, app.signing())
    return disk_image
