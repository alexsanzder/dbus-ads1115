import os


def _read_version() -> str:
    """Read the package version from the repo-root ``version`` file.

    The file contains a single line in the format ``vX.Y.Z``.  We strip the
    leading ``v`` so callers always get a plain PEP-440 version string.
    """
    try:
        _repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(_repo_root, "version")) as _f:
            return _f.read().strip().lstrip("v")
    except Exception:
        return "0.0.0"  # Safety fallback if the version file cannot be read


__version__ = _read_version()
