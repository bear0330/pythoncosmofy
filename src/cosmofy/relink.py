"""Relink a python-ape SDK with static C extensions."""

# std
from __future__ import annotations
from pathlib import Path
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple
import json
import logging
import os
import re
import shutil
import stat
import subprocess
import tempfile
import zipfile

# pkg
from .zipfile2 import ZipFile2

log = logging.getLogger(__name__)

_ARCHES = ("x86_64", "aarch64")
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# apelink stores one deflated table per architecture. ``-s`` only skips
# synthesizing a new table; a table already present in the linked ELF is
# still copied into the fat binary.
_EMBEDDED_SYMTABS = (
    ".symtab",
    ".symtab.amd64",
    ".symtab.arm64",
    ".symtab.ppc64",
    ".symtab.s390x",
    ".symtab.riscv",
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def _require_ident(label: str, value: str) -> str:
    if not _IDENT.match(value):
        raise ValueError(f"{label} is not a C identifier: {value}")

    return value


def _main_source(extensions: List[dict]) -> str:
    lines = [
        '#include "Python.h"',
        '#include "cosmo.h"',
        "",
    ]

    for item in extensions:
        lines.append(f"extern PyObject *{item['init']}(void);")

    lines.extend(["", "int main(int argc, char **argv)", "{"])
    lines.append("    LoadZipArgs(&argc, &argv);")

    for item in extensions:
        module = json.dumps(item["module"])
        lines.append(
            f"    if (PyImport_AppendInittab({module}, {item['init']}) < 0)"
        )
        lines.append("        return 1;")

    lines.extend(["    return Py_BytesMain(argc, argv);", "}", ""])

    return "\n".join(lines)


def _run(cmd: List[str]) -> None:
    """Run a host command. APE tools are started through the shell."""
    with open(cmd[0], "rb") as handle:
        if handle.read(6) == b"MZqFpD":
            cmd = ["/bin/sh", *cmd]

    log.info(" ".join(cmd))
    subprocess.run(cmd, check=True)


def _omit_embedded_symtab(path: Path) -> None:
    """Remove the runtime symbol tables from a fat APE."""
    with ZipFile2(path, "a") as archive:
        present = set(archive.namelist())

        for name in _EMBEDDED_SYMTABS:
            if name in present:
                archive.remove(name)
                log.info(f"omit embedded symbol table: {name}")


def _copy_zip(source: Path, dest: Path) -> None:
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(dest, "a") as dst:
        present = set(dst.namelist())

        for info in src.infolist():
            if info.filename in present:
                continue
            dst.writestr(info, src.read(info.filename))
            present.add(info.filename)


def resolve_superconfigure(sdk: Path, explicit: Optional[Path] = None) -> Path:
    """Find the checkout whose ``cosmopolitan/`` tree supplies cosmocc.

    An explicit directory wins. Otherwise use ``superconfigure/`` beside
    the SDK, which is where ``install-overlay.sh`` clones the tree. When
    the SDK itself lives inside a build tree, that parent is used.
    """
    if explicit is not None:
        chosen = explicit.expanduser().resolve()

        if not chosen.is_dir():
            raise ValueError(
                f"missing superconfigure checkout: {chosen}\n"
                "Run install-overlay.sh or pass --superconfigure."
            )

        return chosen

    sdk = sdk.resolve()
    installed = sdk.parent / "superconfigure"

    if installed.is_dir():
        return installed.resolve()
    if (sdk.parent / "cosmopolitan").is_dir():
        return sdk.parent.resolve()

    raise ValueError(
        "missing superconfigure checkout beside the SDK.\n"
        "Run install-overlay.sh so superconfigure/ exists next to the SDK, "
        "or pass --superconfigure."
    )


def toolchain(superconfigure: Path) -> dict:
    """Compilers and APE tools under ``superconfigure/cosmopolitan``."""
    cosmo = superconfigure / "cosmopolitan"
    bindir = cosmo / "cosmocc" / "bin"

    if not bindir.is_dir():
        raise ValueError(
            f"{superconfigure} has no cosmopolitan/cosmocc/bin.\n"
            "Run .github/scripts/setup and .github/scripts/cosmo in that checkout."
        )

    host = os.uname().machine
    tools = {
        "cc": {arch: bindir / f"{arch}-unknown-cosmo-cc" for arch in _ARCHES},
        "cxx": {arch: bindir / f"{arch}-unknown-cosmo-c++" for arch in _ARCHES},
        "apelink": bindir / "apelink",
        "renamestr": cosmo / "o" / host / "tool" / "build" / "renamestr",
        "ape_elf": {arch: cosmo / "o" / arch / "ape" / "ape.elf" for arch in _ARCHES},
        "ape_m1": cosmo / "ape" / "ape-m1.c",
    }

    missing = []

    for arch in _ARCHES:
        for key in ("cc", "cxx", "ape_elf"):
            if not tools[key][arch].is_file():
                missing.append(str(tools[key][arch]))

    for key in ("apelink", "renamestr", "ape_m1"):
        if not tools[key].is_file():
            missing.append(str(tools[key]))

    if missing:
        raise ValueError(
            "cosmocc in "
            f"{superconfigure} is incomplete. Run .github/scripts/setup and "
            ".github/scripts/cosmo in that checkout.\n" + "\n".join(missing)
        )

    return tools


def rename_prefixes(spec: dict, superconfigure: Path) -> List[str]:
    """Cosmos paths renamestr rewrites to ``/zip``.

    ``link.json`` records the prefixes compiled into the SDK archives.
    Extension objects may also contain the checkout's own cosmos path.
    renamestr accepts four replacements, and a longer path is rewritten
    before a shorter one.
    """
    found = []
    recorded = spec.get("prefixes") or {}

    for arch in _ARCHES:
        value = recorded.get(arch)
        if isinstance(value, str) and value.strip():
            found.append(value.rstrip("/"))

        live = superconfigure / "cosmos" / arch
        if live.is_dir():
            found.append(str(live.resolve()).rstrip("/"))

    unique = []
    seen = set()

    for value in found:
        if value not in seen:
            seen.add(value)
            unique.append(value)

    unique.sort(key=len, reverse=True)

    if not unique:
        raise ValueError(
            "link.json has no prefixes, so relink cannot rewrite cosmos paths to /zip"
        )
    if len(unique) > 4:
        raise ValueError(
            "renamestr accepts at most 4 path rewrites: " + ", ".join(unique)
        )

    return unique


def _project_build_extension(directory: Path) -> Optional[Path]:
    """Return ``scripts/build-extension.sh`` above an extension directory.

    The search starts at the directory and walks at most six parents.
    python-ape and ffl-ape each keep ``scripts/build-extension.sh`` at the
    repository root. An extension with no shared script above it keeps its
    own ``build.sh``.
    """
    current = directory.resolve()

    for _ in range(7):
        candidate = current / "scripts" / "build-extension.sh"
        if candidate.is_file():
            return candidate
        parent = current.parent
        if parent == current:
            return None
        current = parent

    return None


def prepare_extensions(
    sdk: Path, extension_dirs: List[Path], superconfigure: Path
) -> List[Path]:
    """Build each extension, then return Python packages to pack.

    The nearest ``scripts/build-extension.sh`` receives the extension
    directory, the SDK, and the superconfigure checkout. A ``BUILD.mk``
    extension is built by that checkout's ``DOWNLOAD_SOURCE`` rules.
    An extension with no shared script uses its own ``build.sh``, which
    receives the SDK and the checkout.
    """
    packages = []

    for directory in extension_dirs:
        directory = directory.resolve()
        shared = _project_build_extension(directory)

        if shared is not None:
            _run(
                [
                    "/bin/sh",
                    str(shared),
                    str(directory),
                    str(sdk),
                    str(superconfigure),
                ]
            )
        else:
            script = directory / "build.sh"
            if script.is_file():
                _run(["/bin/sh", str(script), str(sdk), str(superconfigure)])

        item = _load(directory / "extension.json")
        relative = item.get("python")

        if not relative:
            continue

        package = (directory / relative).resolve()
        if not package.is_dir():
            raise FileNotFoundError(package)

        packages.append(package)

    return packages


def debug_companions(output: Path) -> Dict[str, Path]:
    """Return cosmocc's companion paths for an apelink output.

    ``app.com`` becomes ``app.com.dbg`` (x86_64) and ``app.aarch64.elf``,
    matching ``${OUTPUT%.com}.com.dbg`` and ``${OUTPUT%.com}.aarch64.elf``.
    """
    text = str(output)
    stem = text[:-4] if text.endswith(".com") else text

    return {
        "x86_64": Path(stem + ".com.dbg"),
        "aarch64": Path(stem + ".aarch64.elf"),
    }


def discard_debug(elves: Optional[Dict[str, Path]]) -> None:
    """Remove a temporary directory that still holds uninstalled ELFs."""
    if not elves:
        return

    for parent in {path.parent for path in elves.values()}:
        if parent.name.startswith("python-relink-dbg-"):
            shutil.rmtree(parent, ignore_errors=True)


def install_debug(output: Path, elves: Dict[str, Path]) -> None:
    """Move unstripped ELFs beside the finished APE."""
    placed = debug_companions(output)

    try:
        for arch, src in elves.items():
            dest = placed[arch]
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                dest.unlink()
            shutil.move(str(src), dest)
            log.info(f"debug symbols: {dest}")
    finally:
        discard_debug(elves)

    log.info(f"cosmoaddr2line {placed['x86_64']} <address>")
    log.info(f"cosmoaddr2line {placed['aarch64']} <address>")


def relink_python(
    sdk: Path,
    extension_dirs: List[Path],
    separate_debug: bool,
    superconfigure: Path,
) -> Tuple[Path, Optional[Dict[str, Path]]]:
    """Link sdk archives with extension archives and return a new python.com.

    ``superconfigure`` is the checkout that contains ``cosmopolitan/``.
    Compilers, apelink, and ape.elf come from that tree. ``link.json``
    prefixes are the cosmos paths compiled into the archives; renamestr
    rewrites those, and the checkout's own cosmos paths, to ``/zip``.

    When ``separate_debug`` is set, apelink is passed ``-s`` and the
    unstripped per-architecture ELFs are returned for ``install_debug``.
    """
    spec = _load(sdk / "link.json")
    tools = toolchain(superconfigure)
    extensions = []

    for directory in extension_dirs:
        directory = directory.resolve()
        item = _load(directory / "extension.json")
        item["root"] = directory
        _require_ident("module", item["module"])
        _require_ident("init", item["init"])

        for arch in _ARCHES:
            archive = directory / item["archives"][arch]
            if not archive.is_file():
                raise FileNotFoundError(archive)

        extensions.append(item)

    dest_file = tempfile.NamedTemporaryFile(
        prefix="python-relink-", suffix=".com", delete=False
    )
    dest_file.close()
    dest = Path(dest_file.name)
    work = Path(tempfile.mkdtemp(prefix="python-relink-"))
    debug_dir: Optional[Path] = None
    saved: Optional[Dict[str, Path]] = None

    try:
        main_c = work / "ape_main.c"
        main_c.write_text(_main_source(extensions))
        elves: Dict[str, Path] = {}

        for arch in _ARCHES:
            obj = work / f"ape_main.{arch}.o"
            elf = work / f"python.{arch}"
            _run(
                [
                    str(tools["cc"][arch]),
                    "-c",
                    "-Os",
                    "-I",
                    str(sdk / spec["pyconfig_dir"][arch]),
                    "-I",
                    str(sdk / spec["include"]),
                    "-o",
                    str(obj),
                    str(main_c),
                ]
            )

            linker = str(tools["cc"][arch])
            if any(item.get("cxx") for item in extensions):
                linker = str(tools["cxx"][arch])

            cmd = [
                linker,
                "-Xlinker",
                "-export-dynamic",
                "-o",
                str(elf),
                str(obj),
            ]
            for item in extensions:
                cmd.append(str(item["root"] / item["archives"][arch]))
            cmd.append(str(sdk / spec["runtime"][arch]))
            _run(cmd)

            rename = [str(tools["renamestr"])]
            for prefix in rename_prefixes(spec, superconfigure):
                rename.extend(["-f", prefix, "-t", "/zip"])
            rename.append(str(elf))
            _run(rename)

            elves[arch] = elf

        apelink = [
            str(tools["apelink"]),
            "-l",
            str(tools["ape_elf"]["x86_64"]),
            "-l",
            str(tools["ape_elf"]["aarch64"]),
            "-M",
            str(tools["ape_m1"]),
            "-o",
            str(dest),
            str(elves["x86_64"]),
            str(elves["aarch64"]),
        ]
        if separate_debug:
            apelink[1:1] = ["-s"]
        _run(apelink)

        if separate_debug:
            debug_dir = Path(tempfile.mkdtemp(prefix="python-relink-dbg-"))
            saved = {}
            for arch, elf in elves.items():
                copy = debug_dir / elf.name
                shutil.copy2(elf, copy)
                saved[arch] = copy

        _copy_zip(sdk / spec["python_com"], dest)

        if separate_debug:
            _omit_embedded_symtab(dest)
    except Exception:
        dest.unlink(missing_ok=True)
        if debug_dir is not None:
            shutil.rmtree(debug_dir, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)

    mode = dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    dest.chmod(mode)
    os.utime(dest, None)
    log.info(f"relinked runtime: {dest}")

    return dest, saved
