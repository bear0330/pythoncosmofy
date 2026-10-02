"""Main entry point."""

# std
from __future__ import annotations
from typing import List
from typing import Optional
import logging
import subprocess
import sys

# pkg
from . import __pubdate__
from . import __version__
from .args import Args
from .args import USAGE
from .bundler import Bundler
from .relink import discard_debug
from .relink import install_debug
from .relink import prepare_extensions
from .relink import relink_python
from .relink import resolve_superconfigure

log_normal = "%(levelname)s: %(message)s"
log_debug = "%(name)s.%(funcName)s: %(levelname)s: %(message)s"
log_verbose = " %(filename)s:%(lineno)s %(funcName)s(): %(levelname)s: %(message)s"
logging.basicConfig(level=logging.INFO, format=log_normal)

log = logging.getLogger(__name__)


def main(argv: Optional[List[str]] = None) -> int:
    """Main entry point."""
    short_usage = "\n" + USAGE[USAGE.find("USAGE") + 5 : USAGE.find("GENERAL")].strip()

    try:
        args = Args.parse((argv or sys.argv)[1:])
    except ValueError as e:
        log.error(e)
        print(short_usage)
        return 1

    if args.debug:
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        formatter = logging.Formatter(log_debug)
        for handler in root_logger.handlers:
            handler.setFormatter(formatter)
        log.debug(args)

    if args.version:
        print(f"{__version__} ({__pubdate__})", flush=True)
        return 0

    if args.help:
        print(USAGE)
        return 0

    if not args.add:
        log.error("You must specify at least one path to add.")
        print(short_usage)
        return 1

    if args.clone and not args.cosmo:
        log.error("--clone is only for pythoncosmofy.com, which sets --cosmo.")
        return 1

    if args.python and not args.python_url and not args.python.is_file():
        log.error(f"missing Python APE: {args.python}")
        return 1

    if args.c_extension and not args.sdk:
        log.error("--c-extension requires --sdk")
        return 1

    if args.superconfigure and not args.sdk:
        log.error("--superconfigure requires --sdk")
        return 1

    if args.separate_debug and not args.c_extension:
        log.error("--separate-debug requires --c-extension")
        return 1

    if args.sdk and not args.sdk.is_dir():
        log.error(f"missing Python SDK: {args.sdk}")
        return 1

    if args.sdk and (args.c_extension or args.superconfigure):
        try:
            args.superconfigure = resolve_superconfigure(args.sdk, args.superconfigure)
        except (OSError, ValueError) as e:
            log.error(e)
            return 1

    debug_elves = None

    try:
        if args.c_extension and args.for_real:
            try:
                args.packages.extend(
                    prepare_extensions(args.sdk, args.c_extension, args.superconfigure)
                )
                args.python, debug_elves = relink_python(
                    args.sdk,
                    args.c_extension,
                    args.separate_debug,
                    args.superconfigure,
                )
            except (OSError, ValueError, subprocess.CalledProcessError) as e:
                log.error(e)
                return 1

            args.python_url = None
            args.clone = False
        elif args.sdk and not args.python and not args.python_url and not args.clone:
            args.python = args.sdk / "python.com"

        output = Bundler(args).run()

        if debug_elves:
            install_debug(output, debug_elves)
            debug_elves = None
    finally:
        discard_debug(debug_elves)

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
