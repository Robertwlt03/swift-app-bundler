"""The app to bundle: its name, its parts and how it is signed, from swift-app-bundler.toml.

Start:  imported by the commands, not started on its own
Needs:  Python 3.13 or newer
Everything comes from swift-app-bundler.toml in the current folder, the package's root. The
signing settings come from the environment or from the local settings file the identity command
writes (local.mk by default, `KEY = value` lines that make can include too); the environment wins.
"""

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# MARK: Settings

SETTINGS_FILE = "swift-app-bundler.toml"
LOCAL_SETTING = re.compile(r"^\s*([A-Z_]+)\s*=\s*(.*?)\s*$")  # SIGN_IDENTITY = My App Dev
# What the environment or the local settings file may set.
SIGNING_NAMES = ("SIGN_IDENTITY", "SIGNING_KEYCHAIN", "SIGNING_KEYCHAIN_PASSWORD",
                 "NOTARY_PROFILE", "BUNDLE_ID", "BUILD_FOLDER")
KNOWN_SETTINGS = {"name", "product", "info_plist", "resources", "icon", "icon_command",
                  "entitlements", "build_folder", "local_settings", "extensions", "release",
                  "identity"}


class SettingsProblem(Exception):
    """The settings cannot be used; the message says why."""


@dataclass(frozen=True)
class Extension:
    """An app extension such as a widget, put into the app's PlugIns folder."""

    product: str  # the executable product of the package
    info_plist: Path
    entitlements: Path | None = None
    id_suffix: str = ""  # an extension's identifier starts with its app's: ".widget"
    texts: tuple[str, ...] = ()  # .strings files only the extension reads; the app leaves them out

    @property
    def bundle_name(self) -> str:
        return f"{self.product}.appex"


@dataclass(frozen=True)
class App:
    root: Path
    name: str  # the app's name: <name>.app, and the disk image's volume
    product: str  # the executable product of the package
    info_plist: Path
    resources: Path | None = None  # its <language>.lproj folders go into the app
    icon: Path | None = None  # a square picture, at least 1024 pixels wide
    icon_command: tuple[str, ...] = ()  # or a command that draws one: {binary}, {output}
    entitlements: Path | None = None
    build_folder: Path = Path("build")
    local_settings: Path = Path("local.mk")
    extensions: tuple[Extension, ...] = ()
    release: dict = field(default_factory=dict, compare=False, hash=False)
    identity: dict = field(default_factory=dict, compare=False, hash=False)

    @property
    def bundle_name(self) -> str:
        return f"{self.name}.app"

    def binary(self, product: str) -> Path:
        return self.root / ".build" / "release" / product

    def signing(self) -> dict[str, str]:
        """The signing settings: the local settings file, overridden by the environment."""
        local = self.root / self.local_settings
        lines = local.read_text().splitlines() if local.exists() else []
        settings = (LOCAL_SETTING.match(line) for line in lines)
        found = {setting[1]: setting[2] for setting in settings
                 if setting and setting[1] in SIGNING_NAMES}
        return found | {name: os.environ[name] for name in SIGNING_NAMES if os.environ.get(name)}


# MARK: Reading


def load(root: Path | None = None) -> App:
    """The app in `root` (the current folder by default), from its swift-app-bundler.toml."""
    root = (root or Path.cwd()).resolve()
    path = root / SETTINGS_FILE
    if not path.exists():
        raise SettingsProblem(f"no {SETTINGS_FILE} in {root}; it names the app and its product")
    try:
        settings = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as error:
        raise SettingsProblem(f"{SETTINGS_FILE} cannot be read: {error}") from error
    unknown = sorted(set(settings) - KNOWN_SETTINGS)
    missing = [key for key in ("name", "product") if key not in settings]
    if unknown or missing:
        raise SettingsProblem(f"{SETTINGS_FILE}: " + "; ".join(
            ([f"unknown setting {', '.join(unknown)}"] if unknown else [])
            + ([f"missing {', '.join(missing)}"] if missing else [])))
    return App(
        root=root,
        name=settings["name"],
        product=settings["product"],
        info_plist=root / settings.get("info_plist", "Info.plist"),
        resources=optional_folder(root, settings.get("resources", "Resources")),
        icon=root / settings["icon"] if "icon" in settings else None,
        icon_command=tuple(settings.get("icon_command", ())),
        entitlements=root / settings["entitlements"] if "entitlements" in settings else None,
        build_folder=Path(settings.get("build_folder", "build")),
        local_settings=Path(settings.get("local_settings", "local.mk")),
        extensions=tuple(extension(root, entry) for entry in settings.get("extensions", [])),
        release=settings.get("release", {}),
        identity=settings.get("identity", {}),
    )


def optional_folder(root: Path, name: str) -> Path | None:
    folder = root / name
    return folder if folder.is_dir() else None


def extension(root: Path, entry: dict) -> Extension:
    if "product" not in entry or "info_plist" not in entry:
        raise SettingsProblem("every [[extensions]] needs product and info_plist")
    return Extension(
        product=entry["product"],
        info_plist=root / entry["info_plist"],
        entitlements=root / entry["entitlements"] if "entitlements" in entry else None,
        id_suffix=entry.get("id_suffix", ""),
        texts=tuple(entry.get("texts", ())),
    )
