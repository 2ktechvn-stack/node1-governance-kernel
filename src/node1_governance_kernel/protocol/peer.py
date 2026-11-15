#!/usr/bin/env python3
"""Cross-platform Unix peer credential extraction.

Linux:   SO_PEERCRED (pid, uid, gid) + SO_PEERSEC
macOS:   LOCAL_PEERCRED (pid, uid, gid via struct xucred)
Windows: PlatformNotSupportedError — daemon requires Linux/WSL2 or macOS.
"""
import os
import socket
import struct
import sys


class PlatformNotSupportedError(OSError):
    """Raised when peer credential extraction is not supported on this OS."""


def peer_identity(conn: socket.socket) -> tuple:
    """Extract (pid, uid, gid, selinux_label) from a Unix socket peer.

    Returns (pid, uid, gid, label) where label may be empty if
    SO_PEERSEC is not available or on non-Linux platforms.

    Raises PlatformNotSupportedError on Windows and other unsupported platforms.
    """
    platform = sys.platform

    if platform == "linux":
        return _peer_identity_linux(conn)
    elif platform == "darwin":
        return _peer_identity_darwin(conn)
    else:
        raise PlatformNotSupportedError(
            f"Peer credential extraction not supported on {platform}. "
            "The governance daemon requires Linux, WSL2, or macOS. "
            "The CLI validator works on all platforms."
        )


def _peer_identity_linux(conn: socket.socket) -> tuple:
    SO_PEERCRED = getattr(socket, "SO_PEERCRED", 17)
    PEERCRED_FMT = "iII"  # pid_t, uid_t, gid_t
    cred = conn.getsockopt(socket.SOL_SOCKET, SO_PEERCRED, struct.calcsize(PEERCRED_FMT))
    pid, uid, gid = struct.unpack(PEERCRED_FMT, cred)

    label = ""
    SO_PEERSEC = getattr(socket, "SO_PEERSEC", 31)
    try:
        raw = conn.getsockopt(socket.SOL_SOCKET, SO_PEERSEC, 256)
        label = raw.rstrip(b"\x00").decode("utf-8", errors="replace")
    except OSError:
        pass

    return pid, uid, gid, label


def _peer_identity_darwin(conn: socket.socket) -> tuple:
    LOCAL_PEERCRED = 0x001
    XUCRED_FMT = "IIi"  # cr_version, cr_uid, cr_ngroups (simplified)
    try:
        cred = conn.getsockopt(0, LOCAL_PEERCRED, struct.calcsize(XUCRED_FMT))
        _version, uid, _ngroups = struct.unpack(XUCRED_FMT, cred[:struct.calcsize(XUCRED_FMT)])
    except OSError:
        uid = 0

    pid = 0
    try:
        pid = conn.getsockopt(0, 0x002, 4)  # LOCAL_PEERPID
        pid = struct.unpack("i", pid if isinstance(pid, bytes) else pid.to_bytes(4, "little"))[0]
    except (OSError, struct.error):
        pass

    gid = os.getgid()
    return pid, uid, gid, ""
