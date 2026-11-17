#!/usr/bin/env python3
"""Run one job step and write its exit code to the file named by STUDIO_EXIT_FILE (the Studio reads it, also after a restart).

  python scripts/run_step.py PROGRAM [ARG ...]

Takes the place of a /bin/sh wrapper so steps run the same way on Windows. The program's output goes where this one's goes. A program that
cannot be started gives 127, as a shell would. A stop request (SIGTERM, or Ctrl-Break on Windows) is passed on to the program.
"""
import os
import shutil
import signal
import subprocess
import sys


# Settings of another Python that must not reach the step: a wrapper (the OSS CAD Suite's tabbypy3) sets them, and a different Python that
# inherits PYTHONHOME stops at once with "No module named 'encodings'". The suite's folders also leave PATH, so "python3" is never its Python.
DROP = ("PYTHONHOME", "PYTHONPATH", "PYTHONEXECUTABLE", "PYTHONSTARTUP", "__PYVENV_LAUNCHER__")


def clean_env(env: dict[str, str]) -> dict[str, str]:
    out = {k: v for k, v in env.items() if k not in DROP}
    if "PATH" in out:
        out["PATH"] = os.pathsep.join(d for d in out["PATH"].split(os.pathsep) if d and "oss-cad-suite" not in d.lower())
    return out


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: run_step.py PROGRAM [ARG ...]", file=sys.stderr)
        return 2
    env = clean_env(dict(os.environ))
    prog = shutil.which(argv[0], path=env.get("PATH")) or argv[0]     # Windows: finds kaggle.exe / uv.exe / a .cmd on PATH
    try:
        proc = subprocess.Popen([prog, *argv[1:]], stdin=subprocess.DEVNULL, env=env)
    except OSError as e:
        print(f"!! cannot start {argv[0]}: {e}", flush=True)
        code = 127
    else:
        def forward(sig, _frame):
            # POSIX: the stop signal goes to the whole group, so the program already has it; this one only stays alive to record the code.
            # Windows: pass Ctrl-Break on (taskkill /F, a moment later, ends anything that ignores it).
            if os.name == "nt":
                try:
                    proc.send_signal(sig)
                except OSError:
                    pass
        for name in ("SIGTERM", "SIGINT", "SIGBREAK"):
            if hasattr(signal, name):
                signal.signal(getattr(signal, name), forward)
        code = proc.wait()
        code = 128 - code if code < 0 else code           # killed by a signal: the shell's 128+n
    out = os.environ.get("STUDIO_EXIT_FILE")
    if out:
        try:
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(f"{code}\n")
        except OSError:
            pass
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
