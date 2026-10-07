"""Undo the most recent "Site update: ..." commit (made by publish_site.py) and push.

Same safety rules as undo_product.py: refuses if index.html/products.json have local edits,
aborts cleanly if the revert conflicts, never force-pushes. Repeat to go further back.
Prints "REVERTED <summary>" or "ERROR <reason>".
"""
import os
import subprocess

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADD = "Site update: "
REVERT = 'Revert "Site update: '


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
        undone, target = set(), None
        for line in git("log", "-n", "200", "--format=%H%x09%s").stdout.splitlines():
            sha, _, subject = line.partition("\t")
            if subject.startswith(REVERT):
                undone.add(subject[len(REVERT):].rstrip('"'))
            elif subject.startswith(ADD):
                name = subject[len(ADD):]
                if name in undone:
                    undone.discard(name)
                    continue
                target = (sha, name)
                break
        if not target:
            return print("ERROR no 'Site update' commit found to revert")
        sha, name = target
        if git("revert", "--no-edit", sha, check=False).returncode != 0:
            git("revert", "--abort", check=False)
            return print(f"ERROR couldn't cleanly revert '{name}' (later edits overlap it). Nothing was changed.")
        git("fetch", "origin", "main")
        push = git("push", "origin", "main", check=False)
        if push.returncode != 0:
            return print("ERROR reverted locally but push failed: " + (push.stderr or push.stdout).strip()[:300])
        print(f"REVERTED {name}")
    except Exception as e:
        print(f"ERROR {e}")


if __name__ == "__main__":
    main()
