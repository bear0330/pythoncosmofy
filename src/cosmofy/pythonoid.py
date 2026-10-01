"""Compile Python source into a Cosmopolitan bundle."""

# std
from __future__ import annotations
from importlib.util import MAGIC_NUMBER
from pathlib import Path
from typing import Optional
from typing import Tuple
from typing import Union
import errno
import marshal
import re
import subprocess
import tempfile

Pkg = Tuple[str, ...]
"""Package information."""

MODULE_SUFFIXES = (".py", ".pyc")
"""Python module suffixes."""

PACKAGE_STEMS = ("__init__", "__main__")
"""File stems that indicate a python package."""

PACKAGE_FILES = tuple(p + s for p in PACKAGE_STEMS for s in MODULE_SUFFIXES)
"""File names that indicate a python package."""

MAIN_FILES = ("__main__.py", "__main__.pyc")
"""File names that indicate python package has a main."""

RE_MAIN = re.compile(
    rb"""
    (^|\n)if\s*(
    __name__\s*==\s*['"]__main__['"]| # written the normal way
    ['"]__main__['"]\s*==\s*__name__) # written in reverse
    """,
    re.VERBOSE,
)
"""Regex for detecting a main section in `bytes`."""


def _pack_uint32(x: Union[int, float]) -> bytes:
    """Convert a 32-bit integer to little-endian."""
    return (int(x) & 0xFFFFFFFF).to_bytes(4, "little")


# Run by the target interpreter. It reads a source file and writes a pyc
# whose magic matches that interpreter, not the process driving the bundler.
_REMOTE_COMPILE = """\
import importlib.util, marshal, pathlib, sys
path = pathlib.Path(sys.argv[1])
out = pathlib.Path(sys.argv[2])
source = path.read_bytes()
st = path.stat()
code = compile(source, str(path), "exec", dont_inherit=True, optimize=-1)
def pack(x):
    return (int(x) & 0xFFFFFFFF).to_bytes(4, "little")
data = bytearray(importlib.util.MAGIC_NUMBER)
data += pack(0) + pack(st.st_mtime) + pack(st.st_size) + marshal.dumps(code)
out.write_bytes(data)
"""

_magic_cache: dict[str, bytes] = {}
_needs_shell = False


def _run_python(python: Path, args: list[str]) -> subprocess.CompletedProcess[bytes]:
    """Run a python.com. Fall back to its shell stub when the kernel has no APE loader."""
    global _needs_shell
    if _needs_shell:
        return subprocess.run(["/bin/sh", str(python), *args], capture_output=True)
    try:
        return subprocess.run([str(python), *args], capture_output=True)
    except OSError as exc:
        if exc.errno != errno.ENOEXEC:
            raise
        _needs_shell = True
        return subprocess.run(["/bin/sh", str(python), *args], capture_output=True)


def _interpreter_magic(python: Path) -> bytes:
    """Return the 4-byte pyc magic of `python`."""
    key = str(python)
    cached = _magic_cache.get(key)
    if cached is not None:
        return cached
    proc = _run_python(
        python,
        [
            "-c",
            "import importlib.util,sys; sys.stdout.buffer.write(importlib.util.MAGIC_NUMBER)",
        ],
    )
    magic = proc.stdout
    if proc.returncode != 0 or len(magic) != 4:
        err = proc.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(
            f"could not read bytecode magic from {python} (exit {proc.returncode}). {err}"
        )
    _magic_cache[key] = magic
    return magic


def _compile_here(path: Path, source: bytes) -> bytearray:
    """Compile with the current interpreter."""
    stats = path.stat()
    code = compile(source, path, "exec", dont_inherit=True, optimize=-1)
    data = bytearray(MAGIC_NUMBER)
    data.extend(_pack_uint32(0))
    data.extend(_pack_uint32(stats.st_mtime))
    data.extend(_pack_uint32(stats.st_size))
    data.extend(marshal.dumps(code))
    return data


def _compile_with(python: Path, path: Path) -> bytearray:
    """Compile with `python` so the pyc magic matches that runtime."""
    handle = tempfile.NamedTemporaryFile(prefix="cosmofy-", suffix=".pyc", delete=False)
    handle.close()
    dest = Path(handle.name)
    try:
        proc = _run_python(python, ["-c", _REMOTE_COMPILE, str(path), str(dest)])
        if proc.returncode != 0 or dest.stat().st_size < 16:
            err = proc.stderr.decode("utf-8", "replace").strip()
            raise RuntimeError(
                f"compile failed with {python} for {path} (exit {proc.returncode}). {err}"
            )
        return bytearray(dest.read_bytes())
    finally:
        dest.unlink(missing_ok=True)


def compile_python(
    path: Path, source: Optional[bytes] = None, python: Optional[Path] = None
) -> bytearray:
    """Return bytecode for `python`, or for this interpreter when it already matches."""
    source = path.read_bytes() if source is None else source
    if python is not None and _interpreter_magic(python) != MAGIC_NUMBER:
        return _compile_with(python, path)
    return _compile_here(path, source)
