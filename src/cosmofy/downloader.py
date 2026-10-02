"""Download a published python.com."""

# std
from __future__ import annotations
from datetime import datetime
from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.request import Request
from urllib.request import urlopen
import logging
import shutil

log = logging.getLogger(__name__)

CHUNK_SIZE = 65536
USER_AGENT = "pythoncosmofy"


def _request(url: str, method: str = "GET") -> Request:
    return Request(url, method=method, headers={"User-Agent": USER_AGENT})


def download(url: str, path: Path) -> Path:
    """Download `url` to `path`."""
    log.info(f"download {url}")
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")

    with urlopen(_request(url)) as response, partial.open("wb") as output:
        while chunk := response.read(CHUNK_SIZE):
            output.write(chunk)

    header = partial.read_bytes()[:6]

    if not header.startswith(b"MZqFpD"):
        partial.unlink(missing_ok=True)
        raise RuntimeError(f"download is not a python.com APE: {url}")

    shutil.move(partial, path)
    return path


def download_if_newer(url: str, path: Path) -> Path:
    """Download `url` when `path` is missing or older than the remote file."""
    if path.is_file():
        local = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)

        try:
            with urlopen(_request(url, "HEAD")) as response:
                stamp = response.headers.get("Last-Modified")

            if stamp:
                remote = parsedate_to_datetime(stamp)

                if remote.tzinfo is None:
                    remote = remote.replace(tzinfo=timezone.utc)

                if remote <= local and path.read_bytes()[:6] == b"MZqFpD":
                    log.info(f"cached {path}")
                    return path
        except OSError as exc:
            log.debug(f"cache check failed: {exc}")

    return download(url, path)
