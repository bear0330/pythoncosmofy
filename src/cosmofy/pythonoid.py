"""Compile Python source into a Cosmopolitan bundle."""

# std
from __future__ import annotations
from importlib.util import MAGIC_NUMBER
from pathlib import Path
from typing import Optional
from typing import Tuple
from typing import Union
import marshal
import re

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


def compile_python(path: Path, source: Optional[bytes] = None) -> bytearray:
    """Return the bytecode."""
    source = path.read_bytes() if source is None else source
    stats = path.stat()
    mtime = stats.st_mtime
    source_size = stats.st_size
    code = compile(source, path, "exec", dont_inherit=True, optimize=-1)

    data = bytearray(MAGIC_NUMBER)
    data.extend(_pack_uint32(0))
    data.extend(_pack_uint32(mtime))
    data.extend(_pack_uint32(source_size))
    data.extend(marshal.dumps(code))
    return data
