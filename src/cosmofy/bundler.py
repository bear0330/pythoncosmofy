"""Cosmofy bundler."""

# std
from __future__ import annotations
from pathlib import Path
from typing import Dict
from typing import Iterator
from typing import Optional
from typing import Set
from typing import Tuple
from typing import Union
import io
import logging
import os
import shlex
import shutil
import stat
import sys
import tempfile
import zipfile

# pkg
from .args import Args
from .pythonoid import compile_python
from .pythonoid import MAIN_FILES
from .pythonoid import PACKAGE_FILES
from .pythonoid import Pkg
from .pythonoid import RE_MAIN
from .zipfile2 import ZipFile2

log = logging.getLogger(__name__)

PATH_COSMOFY = "Lib/site-packages/cosmofy"
"""Path of this package inside a Cosmopolitan Python build."""


def move_executable(src: Path, dest: Path) -> Path:
    """Set the executable bit and move a file."""
    mode = src.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    src.chmod(mode)
    dest.parent.mkdir(parents=True, exist_ok=True)
    # TODO 2024-10-31 @ py3.8 EOL: use `Path` instead of `str`
    shutil.move(str(src), str(dest))
    return dest


def _archive(path: Union[str, Path, io.BytesIO]) -> ZipFile2:
    return ZipFile2(path, mode="a", compression=zipfile.ZIP_DEFLATED, compresslevel=9)


def expand_globs(start: Path, *patterns: str) -> Iterator[Tuple[Path, Set[str]]]:
    """Yield paths of all glob patterns."""
    seen: Set[Path] = set()
    for pattern in patterns:
        if pattern == ".":
            paths = [start]
        elif pattern == "..":
            paths = [start.parent]
        else:
            paths = sorted(start.glob(pattern))

        for path in paths:
            if not path.is_dir():
                if path not in seen:
                    seen.add(path)
                    yield (path, set())
                continue

            for dirname, _, files in os.walk(path):
                folder = Path(dirname)
                if folder not in seen:
                    seen.add(folder)
                    yield (folder, set(files))

                for name in sorted(files):
                    file = folder / name
                    if file not in seen:
                        seen.add(file)
                        yield (file, set())


class Bundler:
    """Wrapper around the bundling process."""

    args: Args
    """Parse command-line arguments."""

    archive: ZipFile2
    """Cosmopolitan APE file."""

    banner: str
    """Log prefix for dry-runs."""

    def __init__(self, args: Args):
        """Construct a bundler."""
        self.args = args
        self.banner = "[DRY RUN] " if args.dry_run else ""

    def fs_copy(self, src: Path, dest: Path) -> Path:
        """Copy a file from `src` to `dest`."""
        log.debug(f"{self.banner}copy: {src} to {dest}")
        if self.args.for_real:
            shutil.copy(src, dest)
        return dest

    def fs_move_executable(self, src: Path, dest: Path) -> Path:
        """Move a file and set its executable bit."""
        log.debug(f"{self.banner}move executable: {src} to {dest}")
        if self.args.for_real:
            move_executable(src, dest)
        return dest

    def setup_temp(self) -> Tuple[Path, Optional[ZipFile2]]:
        """Setup a temporary file and construct a ZipFile (if non-dry-run)."""
        archive = None
        if self.args.for_real:
            temp = Path(tempfile.NamedTemporaryFile(delete=False).name)
        else:
            temp = Path(tempfile.gettempprefix()) / "DRY-RUN"
            archive = _archive(io.BytesIO())
        return temp, archive

    def setup_archive(self) -> ZipFile2:
        """Clone this binary, or copy a local python.com."""
        temp, archive = self.setup_temp()
        if self.args.clone:
            paths = [".args", f"{PATH_COSMOFY}/*"]
            self.fs_copy(Path(sys.executable), temp)
            archive = self.zip_remove(archive or _archive(temp), *paths)
        elif self.args.python:
            log.debug(f"{self.banner}copy runtime: {self.args.python}")
            self.fs_copy(self.args.python, temp)
            archive = archive or _archive(temp)
        else:
            raise ValueError("pass --python PATH, or use --clone")
        return archive

    def process_file(
        self, path: Path, module: Pkg, main: Pkg
    ) -> Tuple[str, Union[bytes, bytearray], Pkg]:
        """Search for main module and compile `.py` files."""
        name, data = path.name, path.read_bytes()
        if not main and name in MAIN_FILES:
            main = module[:-1]
            log.debug(f"found main: {main}")

        # NOTE: We only work on .py files because .pyc files are not searchable.
        if path.suffix == ".py":
            if not main and RE_MAIN.search(data):
                main = module
                log.debug(f"found main: {main}")
            name = path.with_suffix(".pyc").name  # change name
            data = compile_python(path, data)
        return name, data, main

    def zip_add(
        self,
        archive: ZipFile2,
        include: Iterator[Tuple[Path, Set[str]]],
        exclude: Set[Path],
    ) -> Pkg:
        """Add files to `archive` while searching for `main` entry point."""
        modules: Dict[Path, Pkg] = {}
        main: Pkg = tuple()
        pkgs = ("Lib", "site-packages")
        for path, files in include:
            if "__pycache__" in path.parts:
                continue
            if path in exclude:
                log.debug(f"{self.banner}exclude: {path}")
                continue
            if path.is_dir():
                if any(True for p in PACKAGE_FILES if p in files):
                    modules[path] = modules.get(path.parent, tuple()) + (path.name,)
                continue
            # path is a file

            parent = modules.get(path.parent, tuple())
            if not parent and path.name in PACKAGE_FILES:
                parent = (path.parent.name,)
            modules[path] = module = parent + (path.stem,)

            name, data, main = self.process_file(path, module, main)
            dest = "/".join(pkgs + parent + (name,))
            log.info(f"{self.banner}add: {dest}")
            if self.args.for_real:
                archive.add_file(dest, data, 0o644)

        if not main and modules.values():
            main = next(iter(modules.values()))
        return main

    def zip_remove(self, archive: ZipFile2, *patterns: str) -> ZipFile2:
        """Remove glob patterns from the archive."""
        for pattern in patterns:
            log.info(f"{self.banner}remove: {pattern}")
            if self.args.for_real:
                try:
                    archive.remove(pattern)
                except KeyError:
                    log.debug(f"{self.banner}already absent: {pattern}")
        return archive

    def write_args(self, archive: ZipFile2, main: Pkg) -> None:
        """Write special .args file."""
        python_args = ""
        if self.args.args or main:
            python_args = self.args.args or f"-m {'.'.join(main)}"
        if python_args:
            lines = shlex.split(python_args)
            if "..." not in lines:
                lines.append("...")
            log.debug(f"{self.banner}.args = {lines}")
            if self.args.for_real:
                archive.add_file(".args", "\n".join(lines), 0o644)

    def write_output(self, archive: ZipFile2, main: Pkg) -> Path:
        """Move output to appropriate place."""
        if not main:
            main = ("out",)
        elif main[-1] == "__init__":
            main = main[:-1]

        output = self.args.output or Path(f"{main[-1]}.com")
        if archive.filename:
            self.fs_move_executable(Path(archive.filename), output)
        log.info(f"{self.banner}created: {output}")
        return output

    def run(self) -> Path:
        """Run the bundler."""
        archive = self.setup_archive()
        include = expand_globs(Path.cwd(), *self.args.add)
        exclude = set(p[0] for p in expand_globs(Path.cwd(), *self.args.exclude))
        main = self.zip_add(archive, include, exclude)
        self.zip_remove(archive, *self.args.remove)
        self.write_args(archive, main)
        archive.close()  # release the file
        return self.write_output(archive, main)
