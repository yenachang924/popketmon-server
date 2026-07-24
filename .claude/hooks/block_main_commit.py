#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""main 브랜치 직접 커밋 차단 훅 (PreToolUse / matcher: Bash).

CLAUDE.md의 "main에 직접 커밋하지 않는다" 규칙을 문서가 아니라 실행 시점에 강제한다.
stdin으로 들어온 훅 페이로드에서 Bash 명령을 꺼내 '실제 git commit 실행'인지 파싱으로
판별하고, 맞다면 현재 브랜치가 main인지 확인해 exit 2로 차단한다.

판별 기준(문자열에 "commit"이 들어있는지로 보지 않는 이유):
  1) &&, ||, ;, |, 개행 등 셸 연산자로 명령을 세그먼트 단위로 자른다.
     -> `git status && git commit -m x` 처럼 뒤에 숨은 커밋도 잡는다.
  2) 각 세그먼트를 shlex로 토큰화한다(따옴표 인식).
     -> `echo "git commit"` 은 첫 토큰이 echo 라 통과한다.
  3) 첫 토큰이 git 인지 본다(경로/확장자 형태도 basename으로 인정, env/sudo 등 래퍼는 벗김).
  4) 값을 먹는 글로벌 옵션(-C, -c, --git-dir ...)을 건너뛴 뒤 나온 첫 비옵션 토큰,
     즉 서브커맨드가 정확히 "commit"일 때만 커밋으로 본다.
     -> `git log --grep=commit` 은 서브커맨드가 log 라 통과한다.
  * --dry-run 은 실제 커밋을 만들지 않으므로 통과시킨다.

실패 정책(절충안):
  - git commit 이라고 *판별하기 전*의 예외 -> fail-open(exit 0). 훅 버그가 모든 Bash
    명령을 막아 작업이 마비되는 것을 피한다. 대신 로그와 stderr 경고를 남긴다.
  - *판별한 후*의 예외 -> fail-closed(exit 2). 커밋 시도가 확실한 상황에서 브랜치를
    확인할 수 없다면, 규칙이 조용히 무력화되는 것보다 막는 쪽이 안전하다.
  - 통과시킨 모든 예외는 .claude/hooks/hook_errors.log 에 시각과 함께 append 된다.
"""

import json
import os
import shlex
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

# 차단 대상 브랜치. 이 저장소의 기본 브랜치는 main 하나뿐이다.
PROTECTED_BRANCHES = {"main"}

LOG_PATH = Path(__file__).resolve().parent / "hook_errors.log"

# 값을 별도 토큰으로 받는 git 글로벌 옵션. 서브커맨드를 찾을 때 값까지 건너뛰어야 한다.
GIT_GLOBAL_OPTS_WITH_VALUE = {
    "-C",
    "-c",
    "--git-dir",
    "--work-tree",
    "--namespace",
    "--exec-path",
    "--super-prefix",
    "--config-env",
    "--attr-source",
}

# `env FOO=1 git commit`, `sudo git commit` 같은 형태에서 벗겨낼 래퍼 명령들.
WRAPPER_COMMANDS = {"env", "sudo", "command", "nohup", "nice", "stdbuf", "time"}

# shlex(punctuation_chars=True) 가 하나로 묶어주는 셸 연산자들.
PUNCTUATION_CHARS = set("();<>|&")


def _reconfigure_utf8(stream):
    """Windows 기본 코드페이지(cp949)에서 한국어 메시지가 깨지지 않게 UTF-8로 고정."""
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


_reconfigure_utf8(sys.stderr)
_reconfigure_utf8(sys.stdout)


def _log(stage, exc, command=None):
    """예외를 시각과 함께 hook_errors.log 에 append. 로깅 실패는 무시한다."""
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().isoformat(timespec="seconds")
        lines = [
            "[%s] stage=%s error=%s: %s" % (stamp, stage, exc.__class__.__name__, exc)
        ]
        if command is not None:
            lines.append("    command=%r" % (command,))
        tb = traceback.format_exc().rstrip()
        if tb and "NoneType: None" not in tb:
            lines.extend("    " + t for t in tb.splitlines())
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except Exception:
        pass


def _pass_open(stage, exc, command=None):
    """판별 전 예외: 로그를 남기고 경고 한 줄만 출력한 뒤 통과시킨다."""
    _log(stage, exc, command)
    sys.stderr.write(
        "⚠️  [block_main_commit] %s 단계에서 예외가 발생해 검사를 건너뜁니다 "
        "(%s: %s). 자세한 내용은 %s\n" % (stage, exc.__class__.__name__, exc, LOG_PATH)
    )
    sys.exit(0)


def _block(message):
    """PreToolUse 훅에서 exit 2 는 도구 실행을 취소하고 stderr를 모델에 전달한다."""
    sys.stderr.write(message)
    sys.exit(2)


def _strip_wrappers(tokens):
    """env/sudo 같은 래퍼와 `FOO=bar` 형태의 환경변수 지정을 앞에서 제거."""
    i = 0
    while i < len(tokens):
        token = tokens[i]
        base = os.path.basename(token).lower()
        if base.endswith(".exe"):
            base = base[: -len(".exe")]
        if base in WRAPPER_COMMANDS:
            i += 1
            continue
        # `FOO=bar cmd` 형태의 선행 환경변수 지정
        if "=" in token and not token.startswith("-") and token.split("=", 1)[0].isidentifier():
            i += 1
            continue
        break
    return tokens[i:]


def _split_segments(tokens):
    """셸 연산자 토큰을 경계로 명령 세그먼트를 나눈다."""
    segments = []
    current = []
    for token in tokens:
        if token and all(ch in PUNCTUATION_CHARS for ch in token):
            if current:
                segments.append(current)
                current = []
            continue
        current.append(token)
    if current:
        segments.append(current)
    return segments


def _is_git(token):
    base = os.path.basename(token).lower()
    if base.endswith(".exe"):
        base = base[: -len(".exe")]
    return base == "git"


def _git_subcommand(tokens):
    """git 세그먼트에서 서브커맨드를 뽑는다. git 호출이 아니면 None."""
    tokens = _strip_wrappers(tokens)
    if not tokens or not _is_git(tokens[0]):
        return None
    i = 1
    while i < len(tokens):
        token = tokens[i]
        if not token.startswith("-"):
            return token
        # `--git-dir=...` 처럼 값이 붙어 있으면 그 토큰만 건너뛰면 된다.
        if "=" in token:
            i += 1
            continue
        if token in GIT_GLOBAL_OPTS_WITH_VALUE:
            i += 2  # 옵션과 그 값까지 건너뛴다
            continue
        i += 1
    return None


def is_git_commit(command):
    """명령 안에 '실제 커밋을 만드는 git commit'이 있으면 True."""
    lex = shlex.shlex(command, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    tokens = list(lex)
    for segment in _split_segments(tokens):
        if _git_subcommand(segment) != "commit":
            continue
        if "--dry-run" in segment:
            continue  # 실제 커밋을 만들지 않으므로 허용
        return True
    return False


def current_branch(cwd):
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(
            "git rev-parse 실패 (exit %s): %s"
            % (result.returncode, (result.stderr or "").strip())
        )
    return result.stdout.strip()


BLOCK_MESSAGE = """❌ main 브랜치에는 직접 커밋할 수 없습니다.

이 저장소는 CLAUDE.md 커밋 컨벤션에 따라 항상 새 브랜치에서 작업하고
PR을 통해 main에 병합합니다. 직접 커밋은 리뷰 단계를 건너뛰기 때문에 막았습니다.

먼저 브랜치를 만든 뒤 다시 커밋해 주세요:

  git checkout -b <타입>/<간단한-설명>    # 예: git checkout -b feat/add-commit-guard
  git commit -m "..."
  git push -u origin <브랜치명>           # 이후 PR 생성

(이 검사는 .claude/hooks/block_main_commit.py 에서 수행됩니다.)
"""

BRANCH_CHECK_FAILED_MESSAGE = """❌ 커밋을 차단했습니다: 현재 브랜치를 확인할 수 없습니다.

git commit 명령으로 판별했지만 브랜치 검사에 실패했습니다.
main 직접 커밋이 조용히 통과하는 것을 막기 위해 안전하게 차단합니다.

원인: %s

확인해 볼 것:
  - 이 디렉터리가 git 저장소인지: git rev-parse --abbrev-ref HEAD
  - 로그: %s
"""


def main():
    # --- 판별 전 구간: 예외가 나면 fail-open(통과) ---
    raw = None
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
        payload = json.loads(raw) if raw.strip() else {}
    except Exception as exc:
        _pass_open("stdin/JSON 파싱", exc, raw)

    try:
        tool_input = payload.get("tool_input") or {}
        command = tool_input.get("command")
        cwd = payload.get("cwd") or os.getcwd()
    except Exception as exc:
        _pass_open("페이로드 해석", exc, raw)

    if not isinstance(command, str) or not command.strip():
        sys.exit(0)  # 검사할 명령이 없음

    try:
        commit_attempt = is_git_commit(command)
    except Exception as exc:
        _pass_open("명령 파싱", exc, command)

    if not commit_attempt:
        sys.exit(0)

    # --- 판별 후 구간: 여기서부터 예외는 fail-closed(차단) ---
    try:
        branch = current_branch(cwd)
    except Exception as exc:
        _log("브랜치 확인(차단됨)", exc, command)
        _block(BRANCH_CHECK_FAILED_MESSAGE % (exc, LOG_PATH))

    if branch in PROTECTED_BRANCHES:
        _block(BLOCK_MESSAGE)

    sys.exit(0)


if __name__ == "__main__":
    main()
