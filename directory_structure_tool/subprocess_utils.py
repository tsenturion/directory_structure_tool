import os
import subprocess


def hidden_creationflags():
    if os.name != "nt":
        return 0
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _hidden_startupinfo():
    if os.name != "nt" or not hasattr(subprocess, "STARTUPINFO"):
        return None

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0)
    startupinfo.wShowWindow = 0
    return startupinfo


def _with_hidden_window(kwargs):
    if os.name != "nt":
        return kwargs

    updated = dict(kwargs)
    flags = hidden_creationflags()
    if flags:
        updated["creationflags"] = updated.get("creationflags", 0) | flags
    if "startupinfo" not in updated:
        startupinfo = _hidden_startupinfo()
        if startupinfo is not None:
            updated["startupinfo"] = startupinfo
    return updated


def run_hidden(*popenargs, **kwargs):
    return subprocess.run(*popenargs, **_with_hidden_window(kwargs))
