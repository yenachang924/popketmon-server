"""
팝캣/팝케몬 FastAPI 서버 — SQLite 버전 (user_id 식별 추가)
---
설치: pip install fastapi uvicorn   (sqlite3는 파이썬 내장이라 설치 불필요)
실행: python server_deploy.py
→ http://localhost:8000/docs 에서 API 문서 확인

이 버전에서 바뀐 것:
- 이제 'name'이 아니라 'user_id'(기기마다 발급되는 고유키)로 사람을 구분함
- 같은 user_id면 = 같은 기기 = 같은 사람 → 점수 갱신
- 닉네임이 겹쳐도 user_id가 다르면 다른 사람으로 인식
- name은 이제 '랭킹 화면에 보이는 이름'일 뿐, 신원이 아님
"""

import sqlite3
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from datetime import datetime

app = FastAPI(title="팝캣 API (SQLite)", description="냥냥냥 - user_id 식별 버전")

# CORS 설정: 브라우저에서 이 서버로 fetch 요청 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_FILE = "scores.db"


# ── DB 연결 헬퍼 ──
def get_db():
    """scores.db에 연결. 파일이 없으면 자동 생성됨."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row   # 결과를 row["name"]처럼 이름으로 꺼낼 수 있게
    return conn


# ── 서버 시작 시 표 만들기 (없을 때만) ──
def init_db():
    conn = get_db()

    # 옛날 scores 테이블(user_id 칸이 없는 구버전)이 남아있으면 지우고 새로 만든다.
    # 대회 시작 전이고 Render 무료플랜이라 어차피 휘발되는 데이터라서 안전.
    cols = conn.execute("PRAGMA table_info(scores)").fetchall()
    col_names = [c["name"] for c in cols]
    if cols and "user_id" not in col_names:
        conn.execute("DROP TABLE scores")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS scores (
            user_id TEXT PRIMARY KEY,
            name TEXT,
            count INTEGER
        )
    """)
    # 클릭 로그용 표 (선택사항이지만 /stats에서 씀)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pop_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            name TEXT,
            count INTEGER,
            time TEXT
        )
    """)
    conn.commit()
    conn.close()


init_db()   # 서버 켜질 때 한 번 실행


# ── 요청/응답 모델 ──
class PopRequest(BaseModel):
    user_id: str    # 기기 고유키 (프론트의 crypto.randomUUID()로 만든 값)
    name: str       # 플레이어 이름 (화면 표시용)
    count: int      # 현재 총 팝 수


# ── HTML 서빙 ──
@app.get("/", response_class=HTMLResponse)
async def serve_html():
    """팝케몬 게임 페이지 (파일명은 본인 환경에 맞게)"""
    with open("popketmon.html", "r", encoding="utf-8") as f:
        return f.read()


# ── API 엔드포인트들 ──

@app.post("/pop")
async def record_pop(req: PopRequest):
    """
    팝 점수 기록
    POST /pop
    Body: { "user_id": "3f25...", "name": "예나", "count": 42 }
    - 처음 보는 user_id면 INSERT(넣기), 이미 있으면 UPDATE(고치기)
    - 닉네임도 매번 같이 갱신 (사용자가 이름 바꿨을 수도 있으니까)
    """
    conn = get_db()
    conn.execute(
        "INSERT INTO scores (user_id, name, count) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET "
        "name = excluded.name, "
        "count = MAX(scores.count, excluded.count)",
        (req.user_id, req.name, req.count)
    )
    # 로그도 한 줄 남기기
    conn.execute(
        "INSERT INTO pop_logs (user_id, name, count, time) VALUES (?, ?, ?, ?)",
        (req.user_id, req.name, req.count, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    return {"ok": True, "your_count": req.count}


@app.get("/ranking")
async def get_ranking():
    """
    글로벌 랭킹 조회 (상위 10명)
    GET /ranking
    """
    conn = get_db()
    rows = conn.execute(
        "SELECT name, count FROM scores ORDER BY count DESC LIMIT 10"
    ).fetchall()
    total = conn.execute("SELECT COUNT(*) FROM scores").fetchone()[0]
    conn.close()

    ranking = [
        {"rank": i + 1, "name": row["name"], "count": row["count"]}
        for i, row in enumerate(rows)
    ]
    return {"ranking": ranking, "total_players": total}


@app.get("/ranking/{user_id}")
async def get_my_rank(user_id: str):
    """
    특정 플레이어 랭킹 조회 (user_id 기준)
    GET /ranking/3f25...
    - 프론트에서 USER_ID로 조회하면 닉네임이 같아도 '나'를 정확히 찾음
    """
    conn = get_db()
    # 내 점수 가져오기
    row = conn.execute(
        "SELECT name, count FROM scores WHERE user_id = ?", (user_id,)
    ).fetchone()

    if row is None:
        conn.close()
        return {"error": "플레이어를 찾을 수 없어요"}

    my_count = row["count"]
    # 나보다 점수 높은 사람 수 + 1 = 내 등수
    higher = conn.execute(
        "SELECT COUNT(*) FROM scores WHERE count > ?", (my_count,)
    ).fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM scores").fetchone()[0]
    conn.close()

    return {
        "user_id": user_id,
        "name": row["name"],
        "count": my_count,
        "rank": higher + 1,
        "total_players": total
    }


@app.delete("/reset/{user_id}")
async def reset_score(user_id: str):
    """
    특정 플레이어 점수 초기화 (user_id 기준)
    DELETE /reset/3f25...
    """
    conn = get_db()
    cursor = conn.execute("DELETE FROM scores WHERE user_id = ?", (user_id,))
    conn.commit()
    deleted = cursor.rowcount   # 삭제된 행 수 (0이면 없던 키)
    conn.close()

    if deleted > 0:
        return {"ok": True, "message": "점수 초기화됨"}
    return {"error": "플레이어 없음"}


@app.get("/stats")
async def get_stats():
    """서버 전체 통계"""
    conn = get_db()
    total_players = conn.execute("SELECT COUNT(*) FROM scores").fetchone()[0]
    # 총 팝 수 = 모든 count의 합 (아무도 없으면 0)
    total_pops = conn.execute(
        "SELECT COALESCE(SUM(count), 0) FROM scores"
    ).fetchone()[0]
    # 최고 점수 플레이어
    top = conn.execute(
        "SELECT name FROM scores ORDER BY count DESC LIMIT 1"
    ).fetchone()
    # 최근 로그 5개
    logs = conn.execute(
        "SELECT name, count, time FROM pop_logs ORDER BY id DESC LIMIT 5"
    ).fetchall()
    conn.close()

    return {
        "total_players": total_players,
        "total_pops": total_pops,
        "top_player": top["name"] if top else None,
        "recent_logs": [dict(row) for row in logs]
    }


# ── 서버 실행 ──
# 로컬: python server_deploy.py → 8000번 포트
# 배포(Render): Render가 PORT 환경변수로 포트를 정해줌 → 그걸 받아서 사용
if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    print(f"🐱 팝캣 FastAPI 서버 시작! (SQLite + user_id) - port {port}")
    uvicorn.run("server_deploy:app", host="0.0.0.0", port=port)
