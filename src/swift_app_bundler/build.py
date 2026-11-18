"""Builds <name>.app from a Swift package: the release binary, Info.plist, translations, icon,
app extensions such as widgets, and a signature with the hardened runtime.

Start:  swift-app-bundler build [--install]
Needs:  macOS with Swift (swift, codesign, sips, iconutil, PlistBuddy)
Without a signing identity the app is signed ad hoc, and macOS asks again for every permission
after each build; with the identity of `swift-app-bundler identity` it keeps them.
release.py builds through build() and signs the disk image through sign().
"""

import plistlib
import shutil
import subprocess
from pathlib import Path

import console_look as console

from swift_app_bundler.settings import App

# MARK: Settings

# The sizes in points macOS asks for in an app icon; each one also comes twice as large for
# Retina screens.
ICON_SIZES = (16, 32, 128, 256, 512)
AD_HOC_IDENTITY = "-"  # signs without a certificate (ad hoc)
PLIST_BUDDY = "/usr/libexec/PlistBuddy"


class StepFailed(Exception):
    """A tool failed: which one, and what it said."""

    def __init__(self, tool: str, output: str) -> None:
        super().__init__(f"{tool} failed")
        self.tool, self.output = tool, output.strip()


# MARK: Steps


def run(command: list[str | Path], folder: Path | None = None) -> str:
    """Runs a command and raises StepFailed with what it printed when it fails."""
    try:
        result = subprocess.run([str(part) for part in command], cwd=folder,
                                capture_output=True, text=True)
    except FileNotFoundError as error:
        raise StepFailed(str(command[0]), f"{command[0]} is not installed") from error
    if result.returncode != 0:
        raise StepFailed(str(command[0]), result.stdout + result.stderr)
    return result.stdout


def compile_products(app: App) -> None:
    status = console.wait("Compiling (release; errors appear below)",
                          ["swift", "build", "--configuration", "release", "--quiet"], app.root)
    if status != 0:
        raise StepFailed("swift build", "the compiler's messages stand above")
    missing = [product for product in (app.product, *(extension.product for extension in
                                                      app.extensions))
               if not app.binary(product).exists()]
    if missing:
        raise StepFailed("swift build", f"the package builds no product {', '.join(missing)}; "
                         "check product in swift-app-bundler.toml")
    console.passed("Compiled", "release")


def assemble(app: App, bundle: Path, bundle_id: str) -> None:
    shutil.rmtree(bundle, ignore_errors=True)
    for folder in ("MacOS", "Resources"):
        (bundle / "Contents" / folder).mkdir(parents=True)
    shutil.copy2(app.binary(app.product), bundle / "Contents" / "MacOS")
    shutil.copy2(app.info_plist, bundle / "Contents" / "Info.plist")
    extension_texts = [text for extension in app.extensions for text in extension.texts]
    for translation in translations(app):
        shutil.copytree(translation, bundle / "Contents" / "Resources" / translation.name,
                        ignore=shutil.ignore_patterns(*extension_texts))
    # A build with another bundle identifier (such as a demo) gets its own permissions and
    # settings, so it never takes over those of the signed app.
    if bundle_id:
        run([PLIST_BUDDY, "-c", f"Set :CFBundleIdentifier {bundle_id}",
             bundle / "Contents" / "Info.plist"])
    console.passed("Put together", bundle_id or "the identifier from Info.plist")


def translations(app: App) -> list[Path]:
    return sorted(app.resources.glob("*.lproj")) if app.resources else []


def add_extensions(app: App, bundle: Path, bundle_id: str, identity: dict[str, str]) -> None:
    """Each extension into PlugIns, with the app's identifier and version, signed before the app,
    so the app's signature covers the signed extensions."""
    app_info = plistlib.loads((bundle / "Contents" / "Info.plist").read_bytes())
    for extension in app.extensions:
        extension_bundle = bundle / "Contents" / "PlugIns" / extension.bundle_name
        for folder in ("MacOS", "Resources"):
            (extension_bundle / "Contents" / folder).mkdir(parents=True)
        shutil.copy2(app.binary(extension.product), extension_bundle / "Contents" / "MacOS")
        info = plistlib.loads(extension.info_plist.read_bytes())
        app_id = bundle_id or app_info["CFBundleIdentifier"]
        info["CFBundleIdentifier"] = app_id + extension.id_suffix
        # The app's version, as far as its Info.plist names one.
        info |= {key: app_info[key] for key in ("CFBundleShortVersionString", "CFBundleVersion")
                 if key in app_info}
        (extension_bundle / "Contents" / "Info.plist").write_bytes(plistlib.dumps(info))
        copy_extension_texts(app, extension.texts, extension_bundle)
        console.passed("Extension added", info["CFBundleIdentifier"])
        sign(extension_bundle, identity, extension.entitlements)


def copy_extension_texts(app: App, texts: tuple[str, ...], extension_bundle: Path) -> None:
    for translation in translations(app):
        language = extension_bundle / "Contents" / "Resources" / translation.name
        language.mkdir()
        for text in (name for name in texts if (translation / name).exists()):
            shutil.copy2(translation / text, language)


def add_icon(app: App, bundle: Path, build_folder: Path) -> None:
    """The icon from a square picture, or drawn by a command such as the app itself."""
    if not app.icon and not app.icon_command:
        return
    picture = app.icon
    if app.icon_command:
        picture = build_folder / "icon.png"
        names = {"binary": str(app.binary(app.product)), "output": str(picture)}
        run([part.format(**names) for part in app.icon_command], app.root)
    icon_set = build_folder / "AppIcon.iconset"
    shutil.rmtree(icon_set, ignore_errors=True)
    icon_set.mkdir(parents=True)
    for size in ICON_SIZES:
        scale_icon(picture, size, icon_set / f"icon_{size}x{size}.png")
        scale_icon(picture, size * 2, icon_set / f"icon_{size}x{size}@2x.png")
    run(["iconutil", "--convert", "icns", icon_set,
         "--output", bundle / "Contents" / "Resources" / "AppIcon.icns"])
    console.passed("Icon drawn", f"{len(ICON_SIZES)} sizes, each also for Retina")


def scale_icon(picture: Path, pixels: int, destination: Path) -> None:
    run(["sips", "--resampleHeightWidth", str(pixels), str(pixels), picture, "--out", destination])


def sign(target: Path, signing: dict[str, str], entitlements: Path | None = None) -> None:
    """With a fixed identity macOS keeps granted permissions across rebuilds; ad hoc it asks
    again after every build. `swift-app-bundler identity` creates one."""
    identity = signing.get("SIGN_IDENTITY") or AD_HOC_IDENTITY
    options = ["--force", "--options", "runtime", "--sign", identity]
    if entitlements:
        options += ["--entitlements", entitlements]
    keychain = signing.get("SIGNING_KEYCHAIN", "")
    if keychain and identity != AD_HOC_IDENTITY:
        run(["security", "unlock-keychain", "-p", signing.get("SIGNING_KEYCHAIN_PASSWORD", ""),
             keychain])
        options += ["--keychain", keychain]
    run(["codesign", *options, target])
    signer = "ad hoc" if identity == AD_HOC_IDENTITY else identity
    console.passed("Signed", f"{target.name}, {signer}")


def build(app: App, release_folder: Path | None = None) -> Path:
    """The signed app in the build folder; for a release in the given folder, and always with
    the identifier of Info.plist, so a BUNDLE_ID meant for a demo never ships."""
    signing = app.signing()
    folder = release_folder or app.root / signing.get("BUILD_FOLDER", str(app.build_folder))
    bundle = folder / app.bundle_name
    bundle_id = "" if release_folder else signing.get("BUNDLE_ID", "")
    compile_products(app)
    assemble(app, bundle, bundle_id)
    add_icon(app, bundle, folder)
    add_extensions(app, bundle, bundle_id, signing)
    sign(bundle, signing, app.entitlements)
    return bundle


def install(bundle: Path) -> Path:
    """A copy in ~/Applications; the built copy's extensions are unregistered, so only the
    installed app offers them."""
    installed = Path.home() / "Applications" / bundle.name
    shutil.rmtree(installed, ignore_errors=True)
    installed.parent.mkdir(exist_ok=True)
    shutil.copytree(bundle, installed, symlinks=True)
    for extension in sorted((bundle / "Contents" / "PlugIns").glob("*.appex")):
        subprocess.run(["pluginkit", "-r", str(extension)], capture_output=True)
    return installed


def shown(app: App, path: Path) -> str:
    """A path inside the package as the package sees it, such as build/My App.app."""
    return str(path.relative_to(app.root) if path.is_relative_to(app.root) else path)
