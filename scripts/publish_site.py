"""Publish whatever site edits are sitting in the working tree (index.html / products.json).

Validates (JSON.parse of SITE_DATA + products.json, node --check of the main script),
commits ONLY those two files, rebases onto origin/main, and pushes so Vercel redeploys.
Never force-pushes. With --install <file> it first copies that file over index.html
(used when a downloaded admin "Publish" file is sent to the Telegram bot).

Usage: publish_site.py "<commit summary>" [--install <path-to-index.html>]
Prints one result line: "PUBLISHED <sha> <summary>", "NOTHING", or "ERROR <reason>".
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIX = "Site update: "
FILES = ["index.html", "products.json"]


def git(*args, check=True):
    r = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {(r.stderr or r.stdout).strip()[:300]}")
    return r


def validate(index_text, products_text):
    m = re.search(r'id="SITE_DATA"[^>]*>(.*?)</script>', index_text, re.S)
    if not m:
        raise RuntimeError("SITE_DATA block missing from index.html")
    json.loads(m.group(1))
    json.loads(products_text)
    node = shutil.which("node")
    if not node:
        return
    scripts = [s for s in re.findall(r"<script(?![^>]*\bsrc=)(?![^>]*type=\"application/json\")[^>]*>(.*?)</script>", index_text, re.S) if s.strip()]
    if not scripts:
        raise RuntimeError("main <script> block not found")
    main_script = max(scripts, key=len)
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf8") as f:
        f.write(main_script)
    try:
        r = subprocess.run([node, "--check", f.name], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError("node --check failed: " + r.stderr.strip()[:400])
    finally:
        os.unlink(f.name)


def main():
    args = sys.argv[1:]
    install = None
    if "--install" in args:
        i = args.index("--install")
        install = args[i + 1]
        del args[i:i + 2]
    summary = (args[0] if args else "").strip().replace("\n", " ")[:90] or "manual edits"
    try:
        if install:
            new = open(install, encoding="utf8").read()
            validate(new, open(os.path.join(REPO, "products.json"), encoding="utf8").read())
            if "chrome-extension://" in new:
                raise RuntimeError("file contains chrome-extension:// junk (browser-tab contamination); not installing it")
            shutil.copyfile(install, os.path.join(REPO, "index.html"))
        validate(open(os.path.join(REPO, "index.html"), encoding="utf8").read(),
                 open(os.path.join(REPO, "products.json"), encoding="utf8").read())
        if not git("status", "--porcelain", "--", *FILES).stdout.strip():
            return print("NOTHING")
        git("add", *FILES)
        git("commit", "-m", f"{PREFIX}{summary}\n\nCo-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>")
        git("pull", "--rebase", "--autostash", "origin", "main")
        push = git("push", "origin", "main", check=False)
        if push.returncode != 0:
            return print("ERROR committed locally but push failed: " + (push.stderr or push.stdout).strip()[:300])
        print(f"PUBLISHED {git('rev-parse', '--short', 'HEAD').stdout.strip()} {summary}")
    except Exception as e:
        print(f"ERROR {e}")


if __name__ == "__main__":
    main()
