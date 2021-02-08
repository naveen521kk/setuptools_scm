import os
import subprocess
import tarfile
import logging
from .file_finder import scm_find_files
from .file_finder import is_toplevel_acceptable
from .utils import trace

log = logging.getLogger(__name__)


def _git_toplevel(path):
    try:
        cwd = os.path.abspath(path or ".")
        with open(os.devnull, "wb") as devnull:
            out = subprocess.check_output(
                ["git", "rev-parse", "--show-prefix"],
                cwd=cwd,
                universal_newlines=True,
                stderr=devnull,
            )
        out = out.strip()
        if not out:
            out = cwd
        else:
            cwd_parents = []
            out_parents = ["."]
            while True:
                if os.path.abspath(os.path.join(cwd, os.pardir)) != cwd:
                    cwd = os.path.abspath(os.path.join(cwd, os.pardir))
                    cwd_parents.append(cwd)
                else:
                    break
            while True:
                if os.path.basename(out) != "":
                    out = os.path.join(out, os.pardir)
                    out_parents.append(out)
                else:
                    break
            out = str(cwd_parents[len(out_parents) - 1])
        trace("find files toplevel", out)
        return os.path.normcase(os.path.realpath(out.strip()))
    except subprocess.CalledProcessError:
        # git returned error, we are not in a git repo
        return None
    except OSError:
        # git command not found, probably
        return None


def _git_interpret_archive(fd, toplevel):
    with tarfile.open(fileobj=fd, mode="r|*") as tf:
        git_files = set()
        git_dirs = {toplevel}
        for member in tf.getmembers():
            name = os.path.normcase(member.name).replace("/", os.path.sep)
            if member.type == tarfile.DIRTYPE:
                git_dirs.add(name)
            else:
                git_files.add(name)
        return git_files, git_dirs


def _git_ls_files_and_dirs(toplevel):
    # use git archive instead of git ls-file to honor
    # export-ignore git attribute
    cmd = ["git", "archive", "--prefix", toplevel + os.path.sep, "HEAD"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, cwd=toplevel)
    try:
        try:
            return _git_interpret_archive(proc.stdout, toplevel)
        finally:
            # ensure we avoid resource warnings by cleaning up the process
            proc.stdout.close()
            proc.terminate()
    except Exception:
        if proc.wait() != 0:
            log.exception("listing git files failed - pretending there aren't any")
        return (), ()


def git_find_files(path=""):
    toplevel = _git_toplevel(path)
    if not is_toplevel_acceptable(toplevel):
        return []
    fullpath = os.path.abspath(os.path.normpath(path))
    if not fullpath.startswith(toplevel):
        trace("toplevel mismatch", toplevel, fullpath)
    git_files, git_dirs = _git_ls_files_and_dirs(toplevel)
    return scm_find_files(path, git_files, git_dirs)
