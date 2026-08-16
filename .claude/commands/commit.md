---
description: 변경사항을 컨벤션에 맞게 커밋
allowed-tools: Bash(git:*)
---

현재 브랜치: !`git rev-parse --abbrev-ref HEAD`
현재 상태: !`git status`
변경 내용: !`git diff --staged`

**커밋 전 브랜치 확인 (필수)**
위 "현재 브랜치"가 `main`이면 절대 커밋하지 마.
대신 변경 내용에 맞는 브랜치 이름(예: `feat/...`, `fix/...`, `docs/...`)을 제안하고,
`git checkout -b <브랜치명>` 실행 여부를 나에게 먼저 물어봐. 승인 후에만 브랜치를 만들고 커밋해.
(PreToolUse 훅 `.claude/hooks/block_main_commit.py`가 main 커밋을 실제로 차단하지만,
훅에 의존하지 말고 여기서 먼저 확인할 것.)

브랜치가 main이 아니면, 위 변경을 Conventional Commits 형식
(feat/fix/docs...)으로 커밋해줘.
제목은 한 줄, 본문에 "왜"를 적어줘.
