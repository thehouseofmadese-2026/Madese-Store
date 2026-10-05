"""Undo the most recent product the agent published.

Finds the newest "Add product: <name>" commit on main that hasn't already been
undone, reverts it (git revert, so history is kept and it can itself be
reverted), and pushes so Vercel redeploys without that product. Calling it
again undoes the one before, and so on.

Safe by design: refuses if index.html/products.json have local edits, aborts
the revert cleanly if later changes to those files make it conflict, and never
force-pushes.

Prints one result line: "UNDONE <name>" or "ERROR <reason>".
"""
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADD = "Add product: "
REVERT = 'Revert "Add product: '


def git(*args, check=True):
    r = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {(r.stderr or r.stdout).strip()[:300]}")
    return r


def main():
    try:
        if git("status", "--porcelain", "--", "index.html", "products.json").stdout.strip():
            return print("ERROR index.html/products.json have uncommitted local changes; not touching them")
        git("pull", "--rebase", "--autostash", "origin", "main")

        log = git("log", "-n", "200", "--format=%H%x09%s").stdout.splitlines()
        already_undone = set()
        target = None
        for line in log:  # newest first
            sha, _, subject = line.partition("\t")
            if subject.startswith(REVERT):
                already_undone.add(subject[len(REVERT):].rstrip('"'))
            elif subject.startswith(ADD):
                name = subject[len(ADD):]
                if name in already_undone:
                    already_undone.discard(name)  # this one was undone; keep looking further back
                    continue
                target = (sha, name)
                break
        if not target:
            return print("ERROR no agent-published product found to undo")

        sha, name = target
        rv = git("revert", "--no-edit", sha, check=False)
        if rv.returncode != 0:
            git("revert", "--abort", check=False)
            return print(f"ERROR couldn't cleanly undo '{name}' (later edits overlap it). Nothing was changed; ask Claude to remove it by hand.")
        git("fetch", "origin", "main")
        push = git("push", "origin", "main", check=False)
        if push.returncode != 0:
            return print("ERROR undone locally but push failed: " + (push.stderr or push.stdout).strip()[:300])
        print(f"UNDONE {name}")
    except Exception as e:
        print(f"ERROR {e}")


if __name__ == "__main__":
    main()
