"""Tests swift-app-bundler: its settings everywhere, and on a Mac a real build and disk image of
the sample app in Tests/sample.

Start:  python3 -m unittest discover -s Tests (with swift-app-bundler installed: pip install -e .)
Needs:  Python 3.13 or newer; macOS with Swift for the build tests (a minute the first time)
"""

import io
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from swift_app_bundler.__main__ import main
from swift_app_bundler.settings import SettingsProblem, load

SAMPLE = Path(__file__).parent / "sample"


class Folder(unittest.TestCase):
    """Every test works in a folder of its own, as its current folder."""

    def setUp(self) -> None:
        self.here = Path.cwd()
        self.root = Path(tempfile.mkdtemp()).resolve()
        os.chdir(self.root)

    def tearDown(self) -> None:
        os.chdir(self.here)
        shutil.rmtree(self.root)

    def settings(self, text: str) -> None:
        (self.root / "swift-app-bundler.toml").write_text(text)


class SettingsTests(Folder):
    def test_name_and_product_are_needed(self) -> None:
        self.settings('name = "Only a Name"\n')
        with self.assertRaises(SettingsProblem):
            load()

    def test_a_typo_is_named(self) -> None:
        self.settings('name = "App"\nproduct = "App"\nicno = "icon.png"\n')
        with self.assertRaises(SettingsProblem):
            load()

    def test_the_environment_wins_over_the_local_settings(self) -> None:
        self.settings('name = "App"\nproduct = "App"\n')
        (self.root / "local.mk").write_text("SIGN_IDENTITY = Local Dev\nNOTARY_PROFILE = mine\n")
        with mock.patch.dict(os.environ, {"SIGN_IDENTITY": "From Environment"}):
            signing = load().signing()
        self.assertEqual(signing["SIGN_IDENTITY"], "From Environment")
        self.assertEqual(signing["NOTARY_PROFILE"], "mine")

    def test_a_release_without_identity_stops(self) -> None:
        self.settings('name = "App"\nproduct = "App"\n')
        with mock.patch.dict(os.environ, {"SIGN_IDENTITY": ""}), redirect_stdout(io.StringIO()):
            self.assertEqual(main(["release"]), 2)


@unittest.skipUnless(sys.platform == "darwin" and shutil.which("swift"), "needs macOS and Swift")
class BuildTests(Folder):
    """One build and one disk image of the sample app, shared by the tests below."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.folder = Path(tempfile.mkdtemp()).resolve() / "sample"
        shutil.copytree(SAMPLE, cls.folder)
        here = Path.cwd()
        os.chdir(cls.folder)
        try:
            quietly = redirect_stdout(io.StringIO())
            # BUNDLE_ID only for the build: a release keeps the identifier of Info.plist.
            demo = {"SIGN_IDENTITY": "-", "BUNDLE_ID": "io.github.robertwlt03.sample.demo"}
            with mock.patch.dict(os.environ, demo), quietly:
                cls.build_status, cls.release_status = main(["build"]), main(["release"])
        finally:
            os.chdir(here)
        cls.app = cls.folder / "build" / "Sample App.app"

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.folder.parent)

    def test_the_app_holds_its_parts(self) -> None:
        self.assertEqual(self.build_status, 0)
        contents = self.app / "Contents"
        for part in ("MacOS/SampleApp", "Info.plist", "Resources/AppIcon.icns",
                     "Resources/de.lproj/Localizable.strings"):
            self.assertTrue((contents / part).exists(), part)
        self.assertFalse((contents / "Resources/de.lproj/Widget.strings").exists())

    def test_the_widget_gets_the_apps_identifier_and_version(self) -> None:
        widget = self.app / "Contents/PlugIns/SampleWidget.appex/Contents"
        info = plistlib.loads((widget / "Info.plist").read_bytes())
        self.assertEqual(info["CFBundleIdentifier"], "io.github.robertwlt03.sample.demo.widget")
        self.assertEqual(info["CFBundleShortVersionString"], "1.2.3")
        self.assertTrue((widget / "Resources/de.lproj/Widget.strings").exists())

    def test_the_signature_holds(self) -> None:
        result = subprocess.run(["codesign", "--verify", "--strict", "--deep", str(self.app)],
                                capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_release_keeps_the_identifier_of_info_plist(self) -> None:
        released = self.folder / "dist/app/Sample App.app/Contents/Info.plist"
        info = plistlib.loads(released.read_bytes())
        self.assertEqual(info["CFBundleIdentifier"], "io.github.robertwlt03.sample")

    def test_missing_parts_are_named_without_a_traceback(self) -> None:
        broken = self.folder.parent / "broken"
        shutil.copytree(self.folder, broken, symlinks=True)
        settings = broken / "swift-app-bundler.toml"
        here = Path.cwd()
        os.chdir(broken)
        try:
            quietly = redirect_stdout(io.StringIO())
            with mock.patch.dict(os.environ, {"SIGN_IDENTITY": "-"}), quietly:
                settings.write_text(settings.read_text().replace('"docs/guide"', '"docs/gone"'))
                self.assertEqual(main(["release"]), 1)
                settings.write_text(settings.read_text().replace('"SampleApp"', '"SampleAp"'))
                self.assertEqual(main(["build"]), 1)
        finally:
            os.chdir(here)

    def test_the_disk_image_holds_app_link_and_guide(self) -> None:
        self.assertEqual(self.release_status, 0)
        disk_image = self.folder / "dist" / "Sample-App.dmg"
        with tempfile.TemporaryDirectory() as mount:
            subprocess.run(["hdiutil", "attach", "-quiet", "-nobrowse", "-mountpoint", mount,
                            str(disk_image)], check=True)
            try:
                names = sorted(path.name for path in Path(mount).iterdir())
            finally:
                subprocess.run(["hdiutil", "detach", "-quiet", mount], check=True)
        self.assertEqual(names, ["Applications", "Guide", "Sample App.app"])


if __name__ == "__main__":
    unittest.main()
