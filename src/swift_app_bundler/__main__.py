"""The command line: swift-app-bundler build, release and identity.

Start:  swift-app-bundler <command> (or python3 -m swift_app_bundler), in the package's root
Needs:  macOS with Swift; the settings in swift-app-bundler.toml
"""

import argparse
import sys

import console_look as console

from swift_app_bundler import identity, release
from swift_app_bundler.build import StepFailed, build, install, shown
from swift_app_bundler.settings import SettingsProblem, load

# MARK: Commands


def command_line() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="swift-app-bundler", description="Builds, signs and packs a macOS app from a Swift "
                                              "package; settings in swift-app-bundler.toml.")
    commands = parser.add_subparsers(dest="command", required=True)
    built = commands.add_parser("build", help="the signed app in the build folder")
    built.add_argument("--install", action="store_true", help="also copy it to ~/Applications")
    commands.add_parser("release", help="the signed disk image in dist/, notarized if possible")
    commands.add_parser("identity", help="a self-signed signing identity, once per Mac")
    return parser


def run(arguments: argparse.Namespace) -> None:
    app = load()
    if arguments.command == "identity":
        console.heading(f"{app.name} · signing identity", identity.identity_name(app))
        name = identity.create(app)
        console.frame("Signing identity ready", [
            f"{app.local_settings} signs with {name}",
            "Grant the app its permissions once after the next build",
        ], console.SUCCESS)
    elif arguments.command == "release":
        console.heading(f"{app.name} · release", "dist/")
        if not app.signing().get("SIGN_IDENTITY"):
            raise SettingsProblem("no signing identity; create one first: swift-app-bundler "
                                  "identity (or set SIGN_IDENTITY)")
        console.frame("Disk image ready", [shown(app, release.release(app))], console.SUCCESS)
    else:
        console.heading(f"{app.name} · build", app.bundle_name)
        bundle = build(app)
        if arguments.install:
            console.frame("Installed", [str(install(bundle))], console.SUCCESS)
        else:
            console.frame("Built", [shown(app, bundle)], console.SUCCESS)


# MARK: Run


def main(arguments: list[str] | None = None) -> int:
    parsed = command_line().parse_args(arguments)
    try:
        run(parsed)
    except SettingsProblem as problem:
        console.stopped("The settings cannot be used", str(problem))
        return 2
    except StepFailed as failure:
        console.stopped(f"{failure.tool} failed", "", tuple(failure.output.splitlines()[-8:]))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
