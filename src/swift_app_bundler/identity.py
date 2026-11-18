"""Creates a self-signed code-signing identity in a keychain of its own, once per Mac, so every
rebuild keeps the same identity and macOS keeps the permissions it granted, such as Full Disk
Access.

Start:  swift-app-bundler identity
Needs:  macOS; it asks for your password once, to trust the certificate for code signing.
The keychain's random password goes to the local settings file (local.mk by default), which git
must ignore; it protects only this development certificate, and nothing leaves this Mac.
[identity] name (default: "<name> Dev") and keychain (default: "<name>-signing") name both.
"""

import re
import secrets
import subprocess
import tempfile
from pathlib import Path

import console_look as console

from swift_app_bundler.build import StepFailed, run
from swift_app_bundler.settings import App

# MARK: Settings

SIGNING_SETTING = re.compile(r"^(SIGN_IDENTITY|SIGNING_KEYCHAIN|SIGNING_KEYCHAIN_PASSWORD) *=")
SAVED_PASSWORD = re.compile(r"^SIGNING_KEYCHAIN_PASSWORD *= *(.*)$", re.MULTILINE)
VALID_DAYS = 3650  # ten years
KEY_BITS = 2048
CERTIFICATE_SETTINGS = """[req]
distinguished_name = name
x509_extensions = usage
prompt = no
[name]
CN = {name}
[usage]
keyUsage = critical, digitalSignature
extendedKeyUsage = critical, codeSigning
basicConstraints = critical, CA:false
"""


def identity_name(app: App) -> str:
    return app.identity.get("name", f"{app.name} Dev")


def keychain_of(app: App) -> Path:
    name = app.identity.get("keychain", f"{app.name.lower().replace(' ', '-')}-signing")
    return Path.home() / "Library" / "Keychains" / f"{name}.keychain-db"


# MARK: Steps


def saved_settings(app: App) -> str:
    local = app.root / app.local_settings
    return local.read_text() if local.exists() else ""


def unlock_existing_keychain(app: App, keychain: Path) -> str:
    """Opens the keychain with the password the local settings keep, and returns it."""
    saved_password = SAVED_PASSWORD.search(saved_settings(app))
    if not saved_password:
        raise StepFailed("security", f"{app.local_settings} holds no password for {keychain}; "
                         "copy it from the checkout that made it, or start over with: "
                         f"security delete-keychain {keychain}")
    password = saved_password.group(1).strip()
    run(["security", "unlock-keychain", "-p", password, keychain])
    return password


def create_keychain(keychain: Path, password: str) -> None:
    run(["security", "create-keychain", "-p", password, keychain])
    run(["security", "set-keychain-settings", keychain])  # without options: it never locks itself


def create_identity(name: str, password: str, work_folder: Path) -> Path:
    """Key and certificate together as one identity, the form the keychain imports."""
    settings = work_folder / "certificate.conf"
    settings.write_text(CERTIFICATE_SETTINGS.format(name=name))
    key, certificate, identity = (work_folder / file for file in
                                  ("key.pem", "certificate.pem", "identity.p12"))
    run(["/usr/bin/openssl", "req", "-x509", "-newkey", f"rsa:{KEY_BITS}", "-nodes",
         "-days", str(VALID_DAYS), "-config", settings, "-keyout", key, "-out", certificate])
    run(["/usr/bin/openssl", "pkcs12", "-export", "-name", name, "-inkey", key,
         "-in", certificate, "-out", identity, "-passout", f"pass:{password}"])
    return identity


def import_identity(keychain: Path, identity: Path, password: str) -> None:
    # codesign may use the key without asking: the access list (-T) and the partition list.
    run(["security", "import", identity, "-k", keychain, "-P", password,
         "-T", "/usr/bin/codesign"])
    run(["security", "set-key-partition-list", "-S", "apple-tool:,apple:,codesign:", "-s",
         "-k", password, keychain])


def write_settings(app: App, keychain: Path, password: str) -> None:
    """Keeps whatever else the local settings hold and replaces only the signing lines."""
    kept = [
        line for line in saved_settings(app).splitlines() if not SIGNING_SETTING.match(line)
    ]
    signing = [
        f"SIGN_IDENTITY = {identity_name(app)}",
        f"SIGNING_KEYCHAIN = {keychain}",
        f"SIGNING_KEYCHAIN_PASSWORD = {password}",
    ]
    (app.root / app.local_settings).write_text("\n".join(kept + signing) + "\n")
    console.passed("Settings written", str(app.local_settings))


def has_identity(name: str, keychain: Path) -> bool:
    """Whether the keychain holds the identity, which an earlier run may have left out."""
    search = ["security", "find-certificate", "-c", name, str(keychain)]
    return subprocess.run(search, capture_output=True).returncode == 0


def trust_for_code_signing(name: str, keychain: Path, work_folder: Path) -> None:
    """Newer macOS keeps permissions across rebuilds only for a certificate it trusts for code
    signing; without that trust it ties a grant to each build's exact contents."""
    certificate = work_folder / "trusted.pem"
    certificate.write_text(run(["security", "find-certificate", "-c", name, "-p", keychain]))
    # A question to macOS, not a step that may fail: is the certificate trusted already?
    verification = ["security", "verify-cert", "-c", str(certificate), "-p", "codeSign"]
    if subprocess.run(verification, capture_output=True).returncode != 0:
        console.step("macOS now asks once for your password", f"to trust {name} for code signing")
        run(["security", "add-trusted-cert", "-r", "trustRoot", "-p", "codeSign",
             "-k", keychain, certificate])
    console.passed("Trusted for code signing", name)


def create(app: App) -> str:
    """The identity, created or found, trusted for code signing; returns its name."""
    name, keychain = identity_name(app), keychain_of(app)
    # The key files live in a folder that is removed at the end, so they never stay on disk.
    with tempfile.TemporaryDirectory() as folder:
        work_folder = Path(folder)
        if keychain.exists():
            console.step("The signing keychain already exists", str(keychain))
            password = unlock_existing_keychain(app, keychain)
        else:
            password = secrets.token_hex(24)  # made for passwords, from the system's random source
            create_keychain(keychain, password)
            write_settings(app, keychain, password)  # at once, so no failure loses the password
        if not has_identity(name, keychain):
            import_identity(keychain, create_identity(name, password, work_folder), password)
            console.passed("Identity created", "in its own keychain")
        trust_for_code_signing(name, keychain, work_folder)
    return name
