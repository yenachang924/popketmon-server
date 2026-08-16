#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""block_main_commit.py 단위 테스트 러너.

같은 폴더의 샘플 JSON을 훅 스크립트에 파이프로 넣어 exit code를 확인한다.
샘플의 "cwd" 값은 __FIXTURE_MAIN__ / __FIXTURE_FEATURE__ 플레이스홀더로 저장돼 있고,
이 러너가 임시 git 저장소를 만들어 실제 경로로 치환한다. 그래서 이 저장소의 현재
브랜치가 무엇이든 상관없이 언제든 재실행할 수 있다.

실행:
    python .claude/hooks/test_samples/run_tests.py
"""

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
HOOK = HERE.parent / "block_main_commit.py"

# (샘플 파일, 설명, 기대 exit code)
CASES = [
    ("commit_on_main.json", "(a) main에서 git commit", 2),
    ("commit_on_feature_branch.json", "(b) 다른 브랜치에서 git commit", 0),
    ("git_status.json", "(c) git status", 0),
]

# 파싱 판별 기준만 따로 확인하는 케이스 (오탐/미탐 방지)
PARSE_CASES = [
    ("git commit -m 'fix'", True),
    ("git -C . commit -m x", True),
    ("git status && git commit -m x", True),
    ("git commit --dry-run", False),
    ("git log --grep=commit", False),
    ('echo "git commit"', False),
    ("git log --oneline | grep commit", False),
    ("git commit-tree -m x", False),
]


def _make_repo(path, branch):
    """초기 커밋 하나를 가진 fixture git 저장소를 만든다."""
    path.mkdir(parents=True, exist_ok=True)
    run = lambda *args: subprocess.run(
        ["git"] + list(args), cwd=path, capture_output=True, text=True, check=True
    )
    run("init", "-q")
    run("config", "user.email", "test@example.com")
    run("config", "user.name", "hook test")
    run("config", "commit.gpgsign", "false")
    (path / "README.md").write_text("fixture\n", encoding="utf-8")
    run("add", "README.md")
    run("commit", "-q", "-m", "init")
    run("branch", "-M", branch)
    return path


def _rm(path):
    def on_error(func, target, exc_info):
        os.chmod(target, stat.S_IWRITE)
        func(target)

    shutil.rmtree(path, onerror=on_error)


def main():
    tmp = Path(tempfile.mkdtemp(prefix="block-main-commit-test-"))
    failures = 0
    try:
        fixtures = {
            "__FIXTURE_MAIN__": str(_make_repo(tmp / "repo-main", "main")),
            "__FIXTURE_FEATURE__": str(_make_repo(tmp / "repo-feature", "feat/x")),
        }

        print("=== 훅 exit code 테스트 ===")
        for filename, label, expected in CASES:
            payload = json.loads((HERE / filename).read_text(encoding="utf-8"))
            payload["cwd"] = fixtures.get(payload.get("cwd"), payload.get("cwd"))
            proc = subprocess.run(
                [sys.executable, str(HOOK)],
                input=json.dumps(payload).encode("utf-8"),
                capture_output=True,
            )
            ok = proc.returncode == expected
            failures += 0 if ok else 1
            print(
                "%-4s %-34s exit=%d (기대 %d)"
                % ("PASS" if ok else "FAIL", label, proc.returncode, expected)
            )
            stderr = proc.stderr.decode("utf-8", errors="replace").strip()
            if stderr:
                for line in stderr.splitlines():
                    print("       | " + line)

        print("\n=== 명령 판별(파싱) 테스트 ===")
        sys.path.insert(0, str(HOOK.parent))
        from block_main_commit import is_git_commit

        for command, expected_bool in PARSE_CASES:
            actual = is_git_commit(command)
            ok = actual == expected_bool
            failures += 0 if ok else 1
            print(
                "%-4s %-34s -> %s (기대 %s)"
                % ("PASS" if ok else "FAIL", command, actual, expected_bool)
            )
    finally:
        _rm(tmp)

    print("\n실패 %d건" % failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
