"""GitHub ka poora kaam yeh script khud karti hai:
repo banana, files upload karna, secrets daalna, test run shuru karna.

Pehle zaroori: gemini_key.txt, pixabay_key.txt, token.json is folder mein hon.
Phir sirf:   python setup_cloud.py
"""
import pathlib, shutil, subprocess, sys

ROOT = pathlib.Path(__file__).parent
REPO = "open-world-intel"


def run(cmd, **kw):
    print(">", " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT, **kw)


def need(tool, hint):
    if not shutil.which(tool):
        sys.exit(f"{tool} install nahi hai. CMD mein chalao: {hint}\nPhir CMD band karke dobara kholo aur yeh script chalao.")


need("git", "winget install Git.Git")
need("gh", "winget install GitHub.cli")

for f in ("gemini_key.txt", "pixabay_key.txt", "token.json"):
    if not (ROOT / f).exists():
        sys.exit(f"{f} nahi mili. README ke Step 3-4 pehle karo.")

if run(["gh", "auth", "status"], capture_output=True).returncode != 0:
    print("\nGitHub login chahiye. Browser khulega, login karo (naya account bhi bana sakte ho).")
    if run(["gh", "auth", "login", "--web", "--git-protocol", "https"]).returncode != 0:
        sys.exit("GitHub login nahi hua.")
    run(["gh", "auth", "setup-git"])

if not (ROOT / ".git").exists():
    run(["git", "init", "-b", "main"])
run(["git", "config", "user.name", "shorts-bot"])
run(["git", "config", "user.email", "bot@users.noreply.github.com"])
run(["git", "add", "."])
run(["git", "commit", "-m", "Open World Intel"])

r = run(["gh", "repo", "create", REPO, "--public", "--source", ".", "--remote", "origin", "--push"])
if r.returncode != 0:
    sys.exit("Repo nahi bana. Upar wala error mujhe bhej do.")

for name, fname in (("GEMINI_API_KEY", "gemini_key.txt"), ("PIXABAY_API_KEY", "pixabay_key.txt"),
                    ("YT_TOKEN_JSON", "token.json")):
    val = (ROOT / fname).read_text().strip()
    run(["gh", "secret", "set", name], input=val, text=True)

run(["gh", "workflow", "run", "shorts.yml", "-f", "dry_run=1"])
print("\nTayyar! Test run shuru ho gaya. Dekhne ke liye: gh run watch")
print("Green tick aaye to sab theek hai, uske baad roz 5 shorts khud upload hongi.")
