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
from .downloader import download_if_newer
from .pythonoid import compile_python
from .pythonoid import MAIN_FILES
from .pythonoid import MODULE_SUFFIXES
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


def walk_packages(roots: list) -> Iterator[Tuple[Path, Set[str]]]:
    """Yield a package tree. Only Python and typing files are kept."""
    seen: Set[Path] = set()
    suffixes = {".py", ".pyi"}
    for root in roots:
        for dirname, _, files in os.walk(root):
            folder = Path(dirname)
            if "__pycache__" in folder.parts:
                continue

            kept = [
                name
                for name in files
                if name == "py.typed" or Path(name).suffix in suffixes
            ]

            if folder not in seen:
                seen.add(folder)
                yield (folder, set(kept))

            for name in sorted(kept):
                file = folder / name
                if file not in seen:
                    seen.add(file)
                    yield (file, set())


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

    def _download_python(self) -> Path:
        """Cache the requested python.com and use it to compile modules."""
        url = self.args.resolved_python_url()
        dest = self.args.cache_dir() / "python.com"
        log.info(f"{self.banner}python-url: {url}")

        if self.args.for_real:
            download_if_newer(url, dest)
            dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        self.args.python = dest
        return dest

    def setup_archive(self) -> ZipFile2:
        """Download python.com, copy a local one, or clone this binary."""
        temp, archive = self.setup_temp()
        if self.args.python_url:
            self.fs_copy(self._download_python(), temp)
            archive = archive or _archive(temp)
        elif self.args.python:
            log.debug(f"{self.banner}copy runtime: {self.args.python}")
            self.fs_copy(self.args.python, temp)
            archive = archive or _archive(temp)
        elif self.args.clone:
            paths = [".args", f"{PATH_COSMOFY}/*"]
            self.fs_copy(Path(sys.executable), temp)
            archive = self.zip_remove(archive or _archive(temp), *paths)
        else:
            self.fs_copy(self._download_python(), temp)
            archive = archive or _archive(temp)

        return archive

    def process_file(
        self, path: Path, module: Pkg, main: Pkg
    ) -> Tuple[str, Union[bytes, bytearray], Pkg]:
        """Search for main module and compile `.py` files."""
        name = path.name
        data = path.read_bytes()

        if not main and name in MAIN_FILES:
            main = module[:-1]
            log.debug(f"found main: {main}")

        # .pyc files are not searchable, so only .py files can become main.
        if path.suffix == ".py":
            if not main and RE_MAIN.search(data):
                main = module
                log.debug(f"found main: {main}")
            name = path.with_suffix(".pyc").name  # change name
            data = compile_python(path, data, self.args.python)

        return name, data, main

    def _add_roots(self) -> list[Path]:
        """Directories passed on the command line."""
        start = Path.cwd()
        roots: list[Path] = []

        for pattern in self.args.add:
            if pattern == ".":
                roots.append(start.resolve())
            elif pattern == "..":
                roots.append(start.parent.resolve())
            else:
                for path in sorted(start.glob(pattern)):
                    roots.append((path if path.is_dir() else path.parent).resolve())

        return roots

    def _runtime_dest(self, path: Path, roots: list[Path]) -> Optional[str]:
        """Zip path for a ``Lib/`` or ``lib/`` tree, or None for a normal module.

        ``Lib/`` is stored as ``Lib/``. A Linux prefix ``lib/.../site-packages``
        is stored under ``Lib/site-packages``, which is the path this runtime
        imports. Other ``lib/`` files stay at ``lib/``.
        """
        resolved = path.resolve()
        for root in roots:
            try:
                rel = resolved.relative_to(root)
            except ValueError:
                continue
            if not rel.parts or rel.parts[0] not in ("Lib", "lib"):
                continue

            name = rel.name

            if path.is_file() and path.suffix == ".py":
                name = path.with_suffix(".pyc").name

            if path.is_file() and "site-packages" in rel.parts[:-1]:
                idx = rel.parts.index("site-packages")
                tail = rel.parts[idx + 1 : -1] + (name,)
                return "/".join(("Lib", "site-packages") + tail)
            return "/".join(rel.parts[:-1] + (name,))

        return None

    def zip_add(
        self,
        archive: ZipFile2,
        include: Iterator[Tuple[Path, Set[str]]],
        exclude: Set[Path],
        discover_main: bool = True,
    ) -> Pkg:
        """Add files to `archive` while searching for `main` entry point."""
        modules: Dict[Path, Pkg] = {}
        main: Pkg = tuple()
        pkgs = ("Lib", "site-packages")
        roots = self._add_roots()
        for path, files in include:
            if "__pycache__" in path.parts:
                continue

            if path in exclude:
                log.debug(f"{self.banner}exclude: {path}")
                continue

            runtime_dest = self._runtime_dest(path, roots)

            if runtime_dest is not None:
                if path.is_dir():
                    continue

                data: Union[bytes, bytearray] = path.read_bytes()

                if path.suffix == ".py":
                    data = compile_python(path, data, self.args.python)

                log.info(f"{self.banner}add: {runtime_dest}")

                if self.args.for_real:
                    archive.add_file(runtime_dest, data, 0o644)

                continue

            if path.is_dir():
                if any(True for p in PACKAGE_FILES if p in files):
                    modules[path] = modules.get(path.parent, tuple()) + (path.name,)

                continue

            parent = modules.get(path.parent, tuple())

            if not parent and path.name in PACKAGE_FILES:
                parent = (path.parent.name,)

            # README and prepare scripts sit beside Lib/; they are not modules.
            if not parent and path.suffix not in MODULE_SUFFIXES:
                continue

            modules[path] = module = parent + (path.stem,)
            name, data, found = self.process_file(path, module, main)

            if discover_main:
                main = found

            dest = "/".join(pkgs + parent + (name,))
            log.info(f"{self.banner}add: {dest}")

            if self.args.for_real:
                archive.add_file(dest, data, 0o644)

        if discover_main and not main and modules.values():
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

        if self.args.packages:
            self.zip_add(
                archive, walk_packages(self.args.packages), set(), discover_main=False
            )

        self.zip_remove(archive, *self.args.remove)
        self.write_args(archive, main)
        archive.close()

        return self.write_output(archive, main)
