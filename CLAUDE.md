# claude_usage_miniVis

Local visualizer and estimator for Claude Code subscription rate limits. See
README.md for what each file does.

## This repo is public: check for private data before every commit and push

Everything committed here is published. Nothing private may go in:

- no keys, tokens or passwords
- no names or email addresses; commits must use the GitHub noreply address
  (`<id>+<user>@users.noreply.github.com`), never a personal email
- no local paths (`C:\Users\<name>`, drive paths of this machine) and no names
  of other projects
- no real transcript content or real usage data, and no files from `~/.claude`
  (credentials, `usage-mirror.json`, `usage-history.jsonl`, `usage-model.json`)

How to keep it that way:

1. Run `python check_private.py` before committing and again before pushing.
   It scans the working tree and every unpushed commit (message, identity,
   added lines) and exits 1 if it finds anything.
2. The pre-push hook runs the same check and blocks the push. It must be
   enabled in each clone: `git config core.hooksPath .githooks`. Confirm with
   `git config core.hooksPath` before pushing.
3. Personal terms (real name, other project names, host names) belong in
   `.private-terms`, one per line. It is gitignored; never commit it.
4. Stage files by name after reading `git status` and `git diff --cached`;
   never `git add -A` blindly.
5. README examples use made-up run and project names. The checker can't read
   text inside images: open every new or changed screenshot and look.
6. Mark a line `privacy-check: allow` only when it is verifiably not private
   (a placeholder, a documented example).
7. If something private was already pushed, stop and tell the user. It needs a
   history rewrite and rotating any exposed key, not just a follow-up commit.

## Rules the code keeps

- No network calls, no credentials, no API key, zero tokens: everything comes
  from local files.
- `statusline.py` runs on every Claude Code render. It must never raise or
  print a traceback, must stay fast, and must never let a child process hold
  its stdout.
- Files under `~/.claude` hold only what's needed: the mirror and history carry
  no session ids, paths or cost data.
- Writes are atomic (temp file + `os.replace`).
- Windows is the verified platform; macOS/Linux paths exist but are unverified.
