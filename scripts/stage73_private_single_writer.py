"""POSIX single-writer guard for Stage73 trusted-host synthetic rehearsal.

All writers must use the same durable backup-parent directory. This cannot
enforce uniqueness across different hosts, directories, or Drive accounts.
"""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import stat

from archive_private_capture_drive import DriveArchiveRejected
from backup_stage73_private_anchor import _open_parent_directory

LOCK_NAME = ".nexium-stage73-private-single-writer.lock"


@contextmanager
def private_single_writer_lock(backup):
    """Hold an owner-only nonblocking flock across upload and remote readback."""
    directory = _open_parent_directory(Path(backup))
    fd = None
    try:
        try:
            parent = os.fstat(directory)
            if (not stat.S_ISDIR(parent.st_mode)
                    or parent.st_uid != os.geteuid()
                    or stat.S_IMODE(parent.st_mode) & 0o022):
                raise DriveArchiveRejected("unsafe_single_writer_parent")
            flags = (os.O_CREAT | os.O_RDWR | getattr(os, "O_CLOEXEC", 0)
                     | getattr(os, "O_NOFOLLOW", 0))
            fd = os.open(LOCK_NAME, flags, 0o600, dir_fd=directory)
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode)
                    or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_nlink != 1 or info.st_size != 0):
                raise DriveArchiveRejected("unsafe_single_writer_lock")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise DriveArchiveRejected("single_writer_lock_unavailable") from error
        yield
    finally:
        if fd is not None:
            os.close(fd)
        os.close(directory)
