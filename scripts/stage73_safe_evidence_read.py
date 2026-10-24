"""Read diagnostic evidence through one bounded, no-follow file descriptor."""
from __future__ import annotations

import os
from pathlib import Path
import stat
import sys

_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
_FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)
_DARWIN_SYSTEM_ALIASES = {"tmp": "private/tmp", "var": "private/var", "etc": "private/etc"}


def _open_parent(path: Path) -> tuple[int, str]:
    path = Path(path)
    if not path.name or path.name in (".", "..") or ".." in path.parts:
        raise ValueError("unsafe evidence path")
    absolute = path if path.is_absolute() else Path.cwd() / path
    directory = None
    try:
        directory = os.open(absolute.anchor, _DIR_FLAGS)
        for index, component in enumerate(absolute.parts[1:-1]):
            if (sys.platform == "darwin" and index == 0
                    and component in _DARWIN_SYSTEM_ALIASES):
                info = os.stat(component, dir_fd=directory, follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode):
                    expected = _DARWIN_SYSTEM_ALIASES[component]
                    if (info.st_uid != 0
                            or os.readlink(component, dir_fd=directory)
                            not in (expected, "/" + expected)):
                        raise ValueError("unsafe evidence path")
                    private_fd = os.open("private", _DIR_FLAGS, dir_fd=directory)
                    try:
                        next_fd = os.open(component, _DIR_FLAGS, dir_fd=private_fd)
                    finally:
                        os.close(private_fd)
                else:
                    next_fd = os.open(component, _DIR_FLAGS, dir_fd=directory)
            else:
                next_fd = os.open(component, _DIR_FLAGS, dir_fd=directory)
            os.close(directory)
            directory = next_fd
        result = directory
        directory = None
        return result, absolute.name
    except OSError as error:
        raise ValueError("unsafe evidence path") from error
    finally:
        if directory is not None:
            os.close(directory)


def read_bounded_regular_bytes(path: Path, max_bytes: int) -> bytes:
    """Bound the read and reject changed, linked or nonregular evidence files."""
    if type(max_bytes) is not int or max_bytes < 1:
        raise ValueError("invalid evidence size bound")
    parent, name = _open_parent(path)
    try:
        try:
            fd = os.open(name, _FILE_FLAGS, dir_fd=parent)
        except OSError as error:
            raise ValueError("unsafe evidence file") from error
    finally:
        os.close(parent)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > max_bytes:
            raise ValueError("unsafe evidence file")
        data = bytearray()
        while len(data) <= max_bytes:
            fragment = os.read(fd, max_bytes + 1 - len(data))
            if not fragment:
                break
            data.extend(fragment)
        after = os.fstat(fd)
        if (len(data) > max_bytes or len(data) != before.st_size
                or before.st_dev != after.st_dev
                or before.st_ino != after.st_ino
                or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
                or before.st_ctime_ns != after.st_ctime_ns):
            raise ValueError("evidence file changed while reading")
        return bytes(data)
    except OSError as error:
        raise ValueError("unsafe evidence file") from error
    finally:
        os.close(fd)
