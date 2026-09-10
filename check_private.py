"""Privacy check: make sure nothing private gets published by a push.

This repo is public. The check scans what would leave this machine:

  - every commit not on a remote yet: message, author/committer identity and
    the lines it adds
  - run by hand, also the working tree: tracked, staged and untracked files
    that aren't ignored

and looks for

  - secrets: API keys, tokens, private keys, passwords in assignments
  - personal data: email addresses (GitHub/Anthropic noreply are fine) and
    home-directory paths such as C:\\Users\\<name> or /home/<name>
  - private terms: your OS user name and a personal git email, found
    automatically, plus everything in .private-terms -- your name, other
    projects' names, host names. That file is gitignored: the list of what to
    keep private is private too.
  - files that must never be committed: Claude Code credentials, local
    settings, and the data files this tool writes under ~/.claude

Usage:
    python check_private.py              working tree + unpushed commits
    python check_private.py --pre-push   run by .githooks/pre-push (refs on stdin)

Exit status 1 means something was found (and blocks the push). A line that is
verifiably not private can carry the marker `privacy-check: allow`.

Runs git locally and nothing else: no network calls.
"""
import getpass
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
TERMS_FILE = ".private-terms"
ALLOW_MARKER = "privacy-check: allow"
MAX_FILE_BYTES = 2 * 1024 * 1024
ZERO_SHA = re.compile(r"^0+$")

SECRETS = [
    ("Anthropic API key", r"sk-ant-[A-Za-z0-9_\-]{10,}"),
    ("API key (sk-...)", r"\bsk-[A-Za-z0-9]{20,}"),
    ("GitHub token", r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}"),
    ("Slack token", r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"),
    ("AWS access key", r"\bAKIA[0-9A-Z]{16}\b"),
    ("Google API key", r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    ("private key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("bearer token", r"(?i)\bbearer\s+[A-Za-z0-9._\-]{20,}"),
    ("secret in an assignment",
     r"(?i)\b(?:password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token)\b\s*[:=]\s*['\"][^'\"\s]{6,}['\"]"),
]
PERSONAL = [
    ("email address", r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}"),
    ("home directory path",
     r"(?i)\b[A-Z]:[\\/]+Users[\\/]+(?!(?:you|me|user|username|name|public|default)\b)[A-Za-z0-9_.\-]+"
     r"|/(?:Users|home)/(?!(?:you|me|user|username|name|runner)\b)[A-Za-z0-9_.\-]+"),
]
ALLOWED_EMAIL = re.compile(r"(?i)^(?:[\w.+\-]+@users\.noreply\.github\.com|noreply@anthropic\.com|noreply@github\.com)$")
FORBIDDEN_FILE = re.compile(
    r"(?i)(?:^|/)(?:\.credentials\.json|settings\.local\.json|\.private-terms|usage-mirror\.json"
    r"|usage-history(?:\.\d+)?\.jsonl|usage-model\.json|usage-learn\.lock|probe-dump\.jsonl"
    r"|\.env(?:\..+)?|id_rsa|id_ed25519|.+\.pem|.+\.key)$")
# OS user names too generic to search for without drowning in false positives.
GENERIC_USERS = {"user", "admin", "root", "runner", "owner", "dev", "test", "home"}


def git(*args, stdin=None) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, input=stdin, capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError("git %s failed: %s" % (" ".join(args), result.stderr.strip()))
    return result.stdout


def private_terms():
    """(label, compiled pattern) for every term that must not appear."""
    terms = []
    user = getpass.getuser()
    if user and len(user) >= 4 and user.lower() not in GENERIC_USERS:
        terms.append(("your OS user name", user))
    try:
        email = git("config", "user.email").strip()
    except RuntimeError:
        email = ""
    if email and not ALLOWED_EMAIL.match(email):
        terms.append(("your git email", email))
    try:
        with open(os.path.join(ROOT, TERMS_FILE), "r", encoding="utf-8") as fh:
            for number, line in enumerate(fh, 1):
                term = line.strip()
                if term and not term.startswith("#"):
                    terms.append(("%s line %d" % (TERMS_FILE, number), term))
    except OSError:
        pass
    return [(label, re.compile(re.escape(term), re.IGNORECASE)) for label, term in terms]


def mask(text: str) -> str:
    """Enough to find it, not enough to republish it in a terminal log."""
    return text if len(text) <= 4 else text[:2] + "*" * (len(text) - 4) + text[-2:]


class Scanner:
    def __init__(self):
        self.terms = private_terms()
        self.rules = ([(label, re.compile(p)) for label, p in SECRETS]
                      + [(label, re.compile(p)) for label, p in PERSONAL])
        self.findings = []

    def text(self, where: str, text: str) -> None:
        for number, line in enumerate(text.splitlines(), 1):
            if ALLOW_MARKER in line:
                continue
            for label, pattern in self.rules:
                for match in pattern.finditer(line):
                    if label == "email address" and ALLOWED_EMAIL.match(match.group(0)):
                        continue
                    self.findings.append((where, number, label, mask(match.group(0))))
            for label, pattern in self.terms:
                match = pattern.search(line)
                if match:
                    self.findings.append((where, number, "private term (%s)" % label, mask(match.group(0))))

    def file_name(self, where: str, path: str) -> None:
        if FORBIDDEN_FILE.search(path.replace("\\", "/")):
            self.findings.append((where, 0, "file that must never be committed", path))
        self.text(where + " (file name)", path)

    def commit(self, sha: str) -> None:
        short = sha[:9]
        meta = git("show", "-s", "--format=%ae%n%ce", sha).split("\n")
        for role, email in zip(("author", "committer"), meta[:2]):
            if email and not ALLOWED_EMAIL.match(email):
                self.findings.append(("commit %s" % short, 0,
                                      "%s email is not a noreply address" % role, mask(email)))
        self.text("commit %s message" % short, git("show", "-s", "--format=%an%n%cn%n%B", sha))
        for path in git("show", "--name-only", "--format=", sha).splitlines():
            if path:
                self.file_name("commit %s" % short, path)
        current = "?"
        added = []
        for line in git("show", "--format=", "--no-color", "--unified=0", "--no-ext-diff", sha).splitlines():
            if line.startswith("+++ "):
                current = line[6:] if line.startswith("+++ b/") else line[4:]
            elif line.startswith("+") and not line.startswith("+++"):
                added.append((current, line[1:]))
        by_file = {}
        for path, line in added:
            by_file.setdefault(path, []).append(line)
        for path, lines in by_file.items():
            self.text("commit %s %s (added lines)" % (short, path), "\n".join(lines))

    def working_tree(self) -> int:
        paths = [p for p in git("ls-files", "-z", "--cached", "--others", "--exclude-standard").split("\0") if p]
        for path in paths:
            self.file_name(path, path)
            full = os.path.join(ROOT, path)
            try:
                if os.path.getsize(full) > MAX_FILE_BYTES:
                    continue
                with open(full, "rb") as fh:
                    data = fh.read()
            except OSError:
                continue  # listed but deleted in the working tree
            if b"\0" in data[:8000]:
                continue  # binary: look at images yourself, text in pixels can't be scanned
            self.text(path, data.decode("utf-8", "replace"))
        return len(paths)


def unpushed_commits():
    return [sha for sha in git("rev-list", "HEAD", "--not", "--remotes").split() if sha]


def pushed_commits(stdin_text: str):
    """Commits a push would send, from the refs git passes to pre-push."""
    shas = []
    for line in stdin_text.splitlines():
        parts = line.split()
        if len(parts) != 4:
            continue
        _local_ref, local_sha, _remote_ref, remote_sha = parts
        if ZERO_SHA.match(local_sha):
            continue  # deleting a remote branch publishes nothing
        if ZERO_SHA.match(remote_sha):
            shas += git("rev-list", local_sha, "--not", "--remotes").split()
        else:
            shas += git("rev-list", "%s..%s" % (remote_sha, local_sha)).split()
    return list(dict.fromkeys(shas))


def main(argv) -> int:
    scanner = Scanner()
    if "--pre-push" in argv:
        commits = pushed_commits(sys.stdin.read())
        files = 0
    else:
        commits = unpushed_commits()
        files = scanner.working_tree()
    for sha in commits:
        scanner.commit(sha)

    if not scanner.findings:
        print("privacy check: OK -- %d commit(s)%s scanned, nothing private found."
              % (len(commits), " and %d file(s)" % files if files else ""))
        return 0
    print("privacy check: FOUND %d problem(s) -- do not push this:" % len(scanner.findings))
    for where, line, label, excerpt in scanner.findings:
        print("  %s%s: %s: %s" % (where, ":%d" % line if line else "", label, excerpt))
    print("\nFix them (for a commit: amend or rewrite it before pushing). A line that is"
          "\nverifiably not private can be marked with '%s'." % ALLOW_MARKER)
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except RuntimeError as exc:
        # Fail closed: a check that couldn't run must not let the push through.
        print("privacy check: could not run (%s) -- blocking." % exc)
        sys.exit(1)
