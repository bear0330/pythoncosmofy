"""Command-line arguments."""

# std
from __future__ import annotations
from pathlib import Path
from typing import List
from typing import Optional
import dataclasses
import os

DEFAULT_PYTHON_URL = (
    "https://github.com/bear0330/python-ape/releases/latest/download/python.com"
)
"""Latest python.com published by python-ape."""

USAGE = f"""\
cosmofy: bundle a Python program into a Cosmopolitan APE

USAGE

  cosmofy
    [--help] [--version] [--debug] [--dry-run]
    [--python PATH] [--python-url URL] [--clone]
    [--sdk PATH] [--superconfigure PATH]
    [--c-extension DIR]... [--separate-debug]
    [--output PATH] [--args STRING]
    <add>... [--exclude GLOB]... [--remove GLOB]...

GENERAL

  -h, --help        Show this help message and exit.
  --version         Show program version and exit.
  --debug           Show debug messages.
  -n, --dry-run     Do not make any file system changes.

RUNTIME

  --python PATH
    Copy this python.com instead of downloading or cloning.

  --python-url URL
    Download this python.com and copy it.
    On pythoncosmofy.com this overrides --clone.
    [default: {DEFAULT_PYTHON_URL}]

  --clone
    Copy the running pythoncosmofy.com and remove this package.
    pythoncosmofy.com sets this itself.

  --sdk PATH
    Python APE link SDK produced by python-ape's package-sdk.sh.
    Without --c-extension, sdk/python.com is the runtime.

  --superconfigure PATH
    Superconfigure checkout that contains cosmopolitan/. Used when a C
    extension is relinked. cosmocc, apelink, and ape.elf are read from
    that tree. When this is omitted, superconfigure/ beside the SDK is
    used. install-overlay.sh creates that directory.

  --c-extension DIR
    Static extension directory. Requires --sdk. The nearest
    scripts/build-extension.sh above DIR is run with the extension, the
    SDK, and the superconfigure checkout. A BUILD.mk extension is
    downloaded, checked, extracted, and patched by superconfigure's
    DOWNLOAD_SOURCE. Otherwise the sources in extension.json are
    compiled, or a local build.sh is run when the shared script is
    absent. A "python" path in extension.json is packed into
    Lib/site-packages. The runtime is relinked before the app is packed.
    Repeat for more than one extension.

  --separate-debug
    Requires --c-extension. The fat binary omits its embedded symbol
    table. The unstripped ELFs are saved beside an output `app.com`
    as `app.com.dbg` (x86_64) and `app.aarch64.elf`. Point cosmoaddr2line
    at the file for the architecture that crashed.

OUTPUT

  -o PATH, --output PATH
    Path to the output file.
    [default: `<main_module>.com`]

  --args STRING
    Arguments stored in `/zip/.args`.
    [default: `-m <main_module>`]
    `...` is appended so the caller's arguments are forwarded.

FILES

  --add GLOB, <add>
    At least one path or glob to add. Folders are added recursively.
    Files ending in `.py` are compiled.

  -x GLOB, --exclude GLOB
    Skip matching inputs.

  --rm GLOB, --remove GLOB
    Remove matching paths from the output.
"""


@dataclasses.dataclass
class Args:
    help: bool = False
    """Whether to show usage."""

    version: bool = False
    """Whether to show version."""

    debug: bool = False
    """Whether to show debug messages."""

    cosmo: bool = False
    """Whether this process is the bundled pythoncosmofy.com."""

    dry_run: bool = False
    """Whether we should suppress any file-system operations."""

    @property
    def for_real(self) -> bool:
        """Internal value for the opposite of `dry_run`."""
        return not self.dry_run

    @for_real.setter
    def for_real(self, value: bool) -> None:
        """Set dry_run."""
        self.dry_run = not value

    python: Optional[Path] = None
    """Local python.com to copy."""

    python_url: Optional[str] = None
    """Explicit python.com download URL. Unset means the caller did not pass --python-url."""

    clone: bool = False
    """Whether to clone the running binary."""

    sdk: Optional[Path] = None
    """python-ape link SDK. Supplies python.com, or archives when relinking."""

    superconfigure: Optional[Path] = None
    """Checkout that contains cosmopolitan/. Supplies cosmocc when relinking."""

    c_extension: List[Path] = dataclasses.field(default_factory=list)
    """Static extension directories to relink into the runtime."""

    separate_debug: bool = False
    """Whether a relink should omit the symbol table and keep ELF companions."""

    packages: List[Path] = dataclasses.field(default_factory=list)
    """Python packages produced by --c-extension, packed into site-packages."""

    def resolved_python_url(self) -> str:
        """URL used when a python.com is downloaded."""
        return (
            self.python_url
            or os.environ.get("PYTHONCOSMOFY_PYTHON_URL")
            or DEFAULT_PYTHON_URL
        )

    def cache_dir(self) -> Path:
        """Directory for a downloaded python.com."""
        env = os.environ.get("PYTHONCOSMOFY_CACHE")
        return Path(env) if env else Path.home() / ".cache" / "pythoncosmofy"

    output: Optional[Path] = None
    """Path to the output file."""

    args: str = ""
    """Args to pass to Cosmopolitan python."""

    add: List[str] = dataclasses.field(default_factory=list)
    """Globs to add."""

    exclude: List[str] = dataclasses.field(default_factory=list)
    """Globs to exclude."""

    remove: List[str] = dataclasses.field(default_factory=list)
    """Globs to remove."""

    @staticmethod
    def parse(argv: List[str]) -> Args:
        args = Args()
        alias = {
            "-h": "--help",
            "-n": "--dry-run",
            "-o": "--output",
            "-x": "--exclude",
            "--rm": "--remove",
        }
        while argv:
            if argv[0].startswith("-"):
                arg = argv.pop(0)
                arg = alias.get(arg, arg)
            else:
                arg = "--add"

            prop = arg[2:].replace("-", "_")

            if arg in [
                "--clone",
                "--cosmo",
                "--debug",
                "--dry-run",
                "--help",
                "--separate-debug",
                "--version",
            ]:
                setattr(args, prop, True)

            elif arg in ["--args", "--python-url"]:
                if not argv:
                    raise ValueError(f"Expected argument for option: {arg}")
                setattr(args, prop, argv.pop(0))

            elif arg in ["--output", "--python", "--sdk", "--superconfigure"]:
                if not argv:
                    raise ValueError(f"Expected argument for option: {arg}")
                setattr(args, prop, Path(argv.pop(0)))

            elif arg == "--c-extension":
                if not argv:
                    raise ValueError(f"Expected argument for option: {arg}")
                args.c_extension.append(Path(argv.pop(0)))

            elif arg in ["--add", "--exclude", "--remove"]:
                if not argv:
                    raise ValueError(f"Expected argument for option: {arg}")
                getattr(args, prop).append(argv.pop(0))

            else:
                raise ValueError(f"Unknown option: {arg}")
        return args
