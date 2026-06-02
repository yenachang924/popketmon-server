"""
팝캣/팝케몬 FastAPI 서버 — PostgreSQL 버전 (Render 무료 Postgres 영구 저장)
---
설치: pip install fastapi uvicorn "psycopg[binary]"
실행: python server_deploy.py
→ http://localhost:8000/docs 에서 API 문서 확인

이 버전에서 바뀐 것 (SQLite → PostgreSQL):
- 저장소를 컨테이너 안의 scores.db(파일) 대신 Render Postgres로 옮김.
  Render 무료 웹 서비스는 파일 시스템이 휘발성이라, 서버가 잠들었다 깨거나
  재배포될 때마다 SQLite 파일이 통째로 사라져 랭킹이 초기화됐음.
  Postgres는 별도 관리형 DB라 웹 서버가 재시작돼도 데이터가 보존됨.
- 연결은 DATABASE_URL 환경변수로 받음 (Render가 DB 연결 문자열을 주입).
- SQL 플레이스홀더 ? → %s, AUTOINCREMENT → BIGSERIAL 로 변경.
- 식별 방식(user_id가 사람, name은 표시용)과 모든 엔드포인트·응답 형식은 그대로.

주의 — 무료 Render Postgres는 생성 후 30일이 지나면 만료됨.
배포 기간이 30일을 넘기면 그 전에 새 무료 DB를 만들어 데이터를 옮기거나 백업할 것.
"""

import os
import psycopg
from psycopg.rows import dict_row
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from datetime import datetime

app = FastAPI(title="팝캣 API (PostgreSQL)", description="냥냥냥 - user_id 식별 + Postgres 영구 저장")

# CORS 설정: 브라우저에서 이 서버로 fetch 요청 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Render Postgres 연결 문자열. 대시보드의 DB → "Internal Database URL"을 복사해
# 웹 서비스의 환경변수 DATABASE_URL 로 넣으면 됨. (로컬 테스트 시 본인 Postgres URL)
DATABASE_URL = os.environ.get("DATABASE_URL")


# ── DB 연결 헬퍼 ──
def get_db():
    """Postgres에 연결. 결과를 row["name"]처럼 이름으로 꺼낼 수 있게 dict_row 사용."""
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL 환경변수가 설정되지 않았습니다.")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


# ── 서버 시작 시 표 만들기 (없을 때만) ──
def init_db():
    """필요한 테이블을 만든다. 이미 있으면 그대로 둠 (데이터 보존)."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS scores (
                    user_id TEXT PRIMARY KEY,
                    name TEXT,
                    count INTEGER
                )
            """)
            # 클릭 로그용 표 (선택사항이지만 /stats에서 씀)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS pop_logs (
                    id BIGSERIAL PRIMARY KEY,
                    user_id TEXT,
                    name TEXT,
                    count INTEGER,
                    time TEXT
                )
            """)
        conn.commit()


# 서버 켜질 때 한 번 실행. DB가 아직 준비 안 됐을 때 기동 자체가 죽지 않도록 방어.
try:
    init_db()
except Exception as e:
    print(f"⚠️  init_db 실패(앱은 계속 기동): {e}")


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
    - 점수는 MAX(기존, 신규)로 갱신 → 절대 줄지 않음
    - 닉네임도 매번 같이 갱신 (사용자가 이름 바꿨을 수도 있으니까)
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO scores (user_id, name, count) VALUES (%s, %s, %s) "
                "ON CONFLICT (user_id) DO UPDATE SET "
                "name = EXCLUDED.name, "
                "count = GREATEST(scores.count, EXCLUDED.count)",
                (req.user_id, req.name, req.count)
            )
            # 로그도 한 줄 남기기
            cur.execute(
                "INSERT INTO pop_logs (user_id, name, count, time) VALUES (%s, %s, %s, %s)",
                (req.user_id, req.name, req.count, datetime.now().isoformat())
            )
        conn.commit()
    return {"ok": True, "your_count": req.count}


@app.get("/ranking")
async def get_ranking():
    """
    글로벌 랭킹 조회 (상위 10명)
    GET /ranking
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT name, count FROM scores ORDER BY count DESC LIMIT 10"
            )
            rows = cur.fetchall()
            cur.execute("SELECT COUNT(*) AS c FROM scores")
            total = cur.fetchone()["c"]

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
    with get_db() as conn:
        with conn.cursor() as cur:
            # 내 점수 가져오기
            cur.execute(
                "SELECT name, count FROM scores WHERE user_id = %s", (user_id,)
            )
            row = cur.fetchone()

            if row is None:
                return {"error": "플레이어를 찾을 수 없어요"}

            my_count = row["count"]
            # 나보다 점수 높은 사람 수 + 1 = 내 등수
            cur.execute(
                "SELECT COUNT(*) AS c FROM scores WHERE count > %s", (my_count,)
            )
            higher = cur.fetchone()["c"]
            cur.execute("SELECT COUNT(*) AS c FROM scores")
            total = cur.fetchone()["c"]

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
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM scores WHERE user_id = %s", (user_id,))
            deleted = cur.rowcount   # 삭제된 행 수 (0이면 없던 키)
        conn.commit()

    if deleted > 0:
        return {"ok": True, "message": "점수 초기화됨"}
    return {"error": "플레이어 없음"}




@app.get("/stats")
async def get_stats():
    """서버 전체 통계"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM scores")
            total_players = cur.fetchone()["c"]
            # 총 팝 수 = 모든 count의 합 (아무도 없으면 0)
            cur.execute("SELECT COALESCE(SUM(count), 0) AS s FROM scores")
            total_pops = cur.fetchone()["s"]
            # 최고 점수 플레이어
            cur.execute("SELECT name FROM scores ORDER BY count DESC LIMIT 1")
            top = cur.fetchone()
            # 최근 로그 5개
            cur.execute(
                "SELECT name, count, time FROM pop_logs ORDER BY id DESC LIMIT 5"
            )
            logs = cur.fetchall()

    return {
        "total_players": total_players,
        "total_pops": total_pops,
        "top_player": top["name"] if top else None,
        "recent_logs": [dict(row) for row in logs]
    }


# ── 서버 실행 ──
# 로컬: python server_deploy.py → 8000번 포트 (DATABASE_URL 환경변수 필요)
# 배포(Render): Render가 PORT 환경변수로 포트를 정해줌 → 그걸 받아서 사용
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    print(f"🐱 팝캣 FastAPI 서버 시작! (PostgreSQL) - port {port}")
    uvicorn.run("server_deploy:app", host="0.0.0.0", port=port)
