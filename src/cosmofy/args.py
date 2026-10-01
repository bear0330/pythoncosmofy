"""Command-line arguments."""

# std
from __future__ import annotations
from pathlib import Path
from typing import List
from typing import Optional
import dataclasses

USAGE = """\
cosmofy: bundle a Python program into a Cosmopolitan APE

USAGE

  cosmofy
    [--help] [--version] [--debug] [--dry-run]
    [--python PATH] [--clone]
    [--output PATH] [--args STRING]
    <add>... [--exclude GLOB]... [--remove GLOB]...

GENERAL

  -h, --help        Show this help message and exit.
  --version         Show program version and exit.
  --debug           Show debug messages.
  -n, --dry-run     Do not make any file system changes.

RUNTIME

  --python PATH
    Copy this python.com instead of cloning the running binary.
    Bootstrap passes the python-ape release here.

  --clone
    Copy the running pythoncosmofy.com and remove this package.
    pythoncosmofy.com sets this itself.

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

    clone: bool = False
    """Whether to clone the running binary."""

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
                "--version",
            ]:
                setattr(args, prop, True)

            elif arg in ["--args"]:
                if not argv:
                    raise ValueError(f"Expected argument for option: {arg}")
                setattr(args, prop, argv.pop(0))

            elif arg in ["--output", "--python"]:
                if not argv:
                    raise ValueError(f"Expected argument for option: {arg}")
                setattr(args, prop, Path(argv.pop(0)))

            elif arg in ["--add", "--exclude", "--remove"]:
                if not argv:
                    raise ValueError(f"Expected argument for option: {arg}")
                getattr(args, prop).append(argv.pop(0))

            else:
                raise ValueError(f"Unknown option: {arg}")
        return args
