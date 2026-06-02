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

# =============================================================================
#  POPKEMON 분석(Analytics) 모듈
#  -> 이 블록 전체를 server_deploy.py 안, 맨 아래
#     `if __name__ == "__main__":` 줄 "바로 위"에 붙여넣으세요.
#
#  추가되는 것:
#    GET /analytics/raw            : pop_logs 원본 몇 줄 (time 형식 확인용, 가공 X)
#    GET /analytics/daily          : 날짜별 접속자/신규/방문(세션)/클릭증가 (JSON)
#    GET /analytics/users          : 유저별 클릭/이름변경/방문/활동일 (JSON)
#    GET /analytics/user/{user_id} : 특정 유저 상세 + 이름 사용 이력 (JSON)
#    GET /dashboard                : 위 데이터를 네온 테마로 보여주는 대시보드 페이지(HTML)
#
#  주의:
#   - 앱 객체 이름이 `app` 이라고 가정합니다(현재 uvicorn 타깃이 server_deploy:app).
#   - time(TEXT)을 UTC로 저장했다고 보고 한국시간(KST)으로 변환해 "하루"를 가릅니다.
#     (Render 서버 기본 시간대가 UTC라서 보통 맞습니다. 혹시 표가 9시간 어긋나면 알려줘요.)
# =============================================================================

import os
import json
import psycopg
from psycopg.rows import dict_row
from fastapi import HTTPException
from fastapi.responses import HTMLResponse

# 방문(세션) 구분 기준: 같은 유저의 기록이 이 시간 이상 끊기면 "새 방문"으로 셈
SESSION_GAP_MINUTES = 30

# 선택적 보호: Render 환경변수 ANALYTICS_SECRET 를 설정하면
# 분석/대시보드 접근 시 ?key=값 을 요구합니다. 설정 안 하면 누구나 열람 가능.
def _analytics_check_key(key: str):
    secret = os.environ.get("ANALYTICS_SECRET")
    if secret and key != secret:
        raise HTTPException(status_code=403, detail="invalid key")


def _analytics_query(sql: str, params=None):
    """분석 전용: DATABASE_URL로 연결해 SQL을 실행하고 dict 리스트로 반환."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set")
    with psycopg.connect(url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            try:
                return cur.fetchall()
            except psycopg.ProgrammingError:
                return []


# time(TEXT, UTC 가정) -> KST 타임스탬프로 바꾸는 SQL 조각
_KST = "((time)::timestamp AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Seoul')"
# 비어있거나 NULL인 time은 제외(캐스팅 에러 방지)
_VALID = "time IS NOT NULL AND time <> ''"


# ---------------------------------------------------------------------------
# 1) 원본 확인용 (time 형식이 의심되면 제일 먼저 이걸 열어보세요)
# ---------------------------------------------------------------------------
@app.get("/analytics/raw")
def analytics_raw(limit: int = 10, key: str = ""):
    _analytics_check_key(key)
    rows = _analytics_query(
        "SELECT id, user_id, name, count, time FROM pop_logs ORDER BY id DESC LIMIT %s",
        (limit,),
    )
    return {"count": len(rows), "rows": rows}


# ---------------------------------------------------------------------------
# 2) 날짜별 요약
# ---------------------------------------------------------------------------
def _daily_data():
    # (A) 날짜별 활성 유저 / 신규 유저 / 동기화 횟수
    a = _analytics_query(f"""
        WITH base AS (
            SELECT user_id,
                   to_char({_KST}, 'YYYY-MM-DD') AS d
            FROM pop_logs WHERE {_VALID}
        ),
        firsts AS (SELECT user_id, min(d) AS fd FROM base GROUP BY user_id)
        SELECT b.d AS date,
               count(DISTINCT b.user_id) AS active_users,
               count(*) AS total_syncs,
               count(DISTINCT b.user_id) FILTER (WHERE f.fd = b.d) AS new_users
        FROM base b JOIN firsts f ON f.user_id = b.user_id
        GROUP BY b.d ORDER BY b.d;
    """)

    # (B) 날짜별 방문(세션) 수 — 유저별 time 간격으로 추정
    b = _analytics_query(f"""
        WITH base AS (
            SELECT user_id, (time)::timestamp AS ts,
                   to_char({_KST}, 'YYYY-MM-DD') AS d
            FROM pop_logs WHERE {_VALID}
        ),
        g AS (
            SELECT d, ts - LAG(ts) OVER (PARTITION BY user_id ORDER BY ts) AS gap
            FROM base
        )
        SELECT d AS date,
               sum(CASE WHEN gap IS NULL OR gap > interval '{SESSION_GAP_MINUTES} minutes'
                        THEN 1 ELSE 0 END) AS sessions
        FROM g GROUP BY d ORDER BY d;
    """)

    # (C) 날짜별 "그날 늘어난 클릭 수" — 누적 count의 일별 증가분
    c = _analytics_query(f"""
        WITH base AS (
            SELECT user_id, count AS cnt,
                   to_char({_KST}, 'YYYY-MM-DD') AS d
            FROM pop_logs WHERE {_VALID}
        ),
        per_day AS (SELECT user_id, d, max(cnt) AS day_cum FROM base GROUP BY user_id, d),
        with_prev AS (
            SELECT user_id, d, day_cum,
                   LAG(day_cum) OVER (PARTITION BY user_id ORDER BY d) AS prev_cum
            FROM per_day
        )
        SELECT d AS date, sum(day_cum - COALESCE(prev_cum, 0)) AS clicks_gained
        FROM with_prev GROUP BY d ORDER BY d;
    """)

    # 날짜 기준으로 합치기
    by_date = {}
    for r in a:
        by_date[r["date"]] = {
            "date": r["date"],
            "active_users": r["active_users"] or 0,
            "new_users": r["new_users"] or 0,
            "total_syncs": r["total_syncs"] or 0,
            "sessions": 0,
            "clicks_gained": 0,
        }
    for r in b:
        if r["date"] in by_date:
            by_date[r["date"]]["sessions"] = int(r["sessions"] or 0)
    for r in c:
        if r["date"] in by_date:
            by_date[r["date"]]["clicks_gained"] = int(r["clicks_gained"] or 0)
    return sorted(by_date.values(), key=lambda x: x["date"])


@app.get("/analytics/daily")
def analytics_daily(key: str = ""):
    _analytics_check_key(key)
    return {"days": _daily_data()}


# ---------------------------------------------------------------------------
# 3) 유저별 요약
# ---------------------------------------------------------------------------
def _users_data():
    return _analytics_query(f"""
        WITH ordered AS (
            SELECT user_id, name, count AS cnt, (time)::timestamp AS ts,
                   LAG((time)::timestamp) OVER (PARTITION BY user_id ORDER BY (time)::timestamp) AS pts,
                   LAG(name)              OVER (PARTITION BY user_id ORDER BY (time)::timestamp) AS pname
            FROM pop_logs WHERE {_VALID}
        )
        SELECT user_id,
               (array_agg(name ORDER BY ts DESC))[1] AS current_name,
               max(cnt) AS clicks,
               count(DISTINCT name) AS distinct_names,
               sum(CASE WHEN pname IS NOT NULL AND name IS DISTINCT FROM pname
                        THEN 1 ELSE 0 END) AS name_changes,
               sum(CASE WHEN pts IS NULL OR ts - pts > interval '{SESSION_GAP_MINUTES} minutes'
                        THEN 1 ELSE 0 END) AS sessions,
               count(*) AS syncs,
               count(DISTINCT to_char((ts AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Seoul'),
                                      'YYYY-MM-DD')) AS active_days,
               to_char(min(ts) AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Seoul',
                       'YYYY-MM-DD HH24:MI') AS first_seen,
               to_char(max(ts) AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Seoul',
                       'YYYY-MM-DD HH24:MI') AS last_seen
        FROM ordered
        GROUP BY user_id
        ORDER BY clicks DESC;
    """)


@app.get("/analytics/users")
def analytics_users(key: str = ""):
    _analytics_check_key(key)
    return {"users": _users_data()}


@app.get("/analytics/user/{user_id}")
def analytics_user(user_id: str, key: str = ""):
    _analytics_check_key(key)
    rows = [u for u in _users_data() if u["user_id"] == user_id]
    summary = rows[0] if rows else None
    history = _analytics_query(f"""
        SELECT name,
               to_char(min((time)::timestamp) AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Seoul',
                       'YYYY-MM-DD HH24:MI') AS first_used,
               count(*) AS syncs
        FROM pop_logs
        WHERE user_id = %s AND {_VALID}
        GROUP BY name
        ORDER BY min((time)::timestamp);
    """, (user_id,))
    return {"summary": summary, "name_history": history}


# ---------------------------------------------------------------------------
# 4) 대시보드 (HTML) — /dashboard
# ---------------------------------------------------------------------------
_DASHBOARD_HTML = r"""
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>POPKEMON · Analytics</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  :root{ --pink:#ff2d95; --pink2:#ff66b3; --bg:#0a0410; --panel:#15081f; --line:#2a1336; --txt:#f4e9ff; --muted:#a78bb5; }
  *{ box-sizing:border-box; }
  body{ margin:0; background:radial-gradient(1200px 600px at 50% -10%, #1b0a2b, var(--bg)); color:var(--txt);
        font-family:'Segoe UI',Roboto,system-ui,sans-serif; padding:24px; }
  h1{ font-size:26px; letter-spacing:2px; margin:0 0 4px; }
  h1 b{ color:var(--pink); text-shadow:0 0 12px rgba(255,45,149,.7); }
  .sub{ color:var(--muted); font-size:13px; margin-bottom:22px; }
  .cards{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:14px; margin-bottom:24px; }
  .card{ background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:16px 18px;
         box-shadow:0 0 18px rgba(255,45,149,.08) inset; }
  .card .n{ font-size:30px; font-weight:700; color:var(--pink2); text-shadow:0 0 10px rgba(255,102,179,.5); }
  .card .l{ font-size:12px; color:var(--muted); margin-top:4px; letter-spacing:.5px; }
  .panel{ background:var(--panel); border:1px solid var(--line); border-radius:16px; padding:18px 20px; margin-bottom:22px; }
  .panel h2{ font-size:15px; margin:0 0 14px; color:var(--pink2); letter-spacing:1px; }
  canvas{ max-height:300px; }
  table{ width:100%; border-collapse:collapse; font-size:13px; }
  th,td{ text-align:left; padding:9px 10px; border-bottom:1px solid var(--line); white-space:nowrap; }
  th{ color:var(--muted); font-weight:600; font-size:11px; letter-spacing:.6px; }
  tr:hover td{ background:rgba(255,45,149,.06); }
  td.num{ text-align:right; font-variant-numeric:tabular-nums; }
  .rank{ color:var(--pink); font-weight:700; }
  .name{ color:var(--txt); font-weight:600; }
  .uid{ color:#5d4a6b; font-size:10px; }
  .empty{ color:var(--muted); padding:30px; text-align:center; }
  .foot{ color:#4d3a5b; font-size:11px; text-align:center; margin-top:10px; }
</style>
</head>
<body>
  <h1>POP<b>KEMON</b> · ANALYTICS</h1>
  <div class="sub">방문은 30분 이상 끊기면 새 방문으로 셈 · 시간은 한국시간(KST) 기준</div>

  <div class="cards" id="cards"></div>

  <div class="panel">
    <h2>날짜별 추이</h2>
    <canvas id="dailyChart"></canvas>
  </div>

  <div class="panel">
    <h2>유저별 상세 (클릭 많은 순)</h2>
    <div id="tableWrap"></div>
  </div>

  <div class="foot">/analytics/daily · /analytics/users · /analytics/user/{user_id} 로 원본 JSON도 볼 수 있어요</div>

<script>
  const DAILY = /*DAILY_JSON*/;
  const USERS = /*USERS_JSON*/;

  // 요약 카드
  const totalPlayers = USERS.length;
  const totalClicks  = USERS.reduce((s,u)=>s+(u.clicks||0),0);
  const totalSess    = USERS.reduce((s,u)=>s+(u.sessions||0),0);
  const totalNameCh  = USERS.reduce((s,u)=>s+(u.name_changes||0),0);
  const cards = [
    ["총 플레이어", totalPlayers],
    ["총 클릭 수", totalClicks.toLocaleString()],
    ["총 방문(세션)", totalSess.toLocaleString()],
    ["총 이름 변경", totalNameCh.toLocaleString()],
  ];
  document.getElementById('cards').innerHTML = cards.map(c =>
    `<div class="card"><div class="n">${c[1]}</div><div class="l">${c[0]}</div></div>`).join('');

  // 날짜별 차트
  if (DAILY.length){
    new Chart(document.getElementById('dailyChart'), {
      type:'bar',
      data:{
        labels: DAILY.map(d=>d.date),
        datasets:[
          {label:'접속자', data:DAILY.map(d=>d.active_users), backgroundColor:'#ff2d95'},
          {label:'신규',   data:DAILY.map(d=>d.new_users),    backgroundColor:'#9b4dff'},
          {label:'방문(세션)', data:DAILY.map(d=>d.sessions),  backgroundColor:'#ff66b3'},
          {label:'클릭 증가', data:DAILY.map(d=>d.clicks_gained), type:'line',
           borderColor:'#ffd24d', backgroundColor:'#ffd24d', yAxisID:'y1', tension:.3},
        ]
      },
      options:{
        plugins:{ legend:{ labels:{ color:'#f4e9ff' } } },
        scales:{
          x:{ ticks:{color:'#a78bb5'}, grid:{color:'#2a1336'} },
          y:{ ticks:{color:'#a78bb5'}, grid:{color:'#2a1336'}, title:{display:true,text:'명/세션',color:'#a78bb5'} },
          y1:{ position:'right', ticks:{color:'#ffd24d'}, grid:{display:false}, title:{display:true,text:'클릭',color:'#ffd24d'} }
        }
      }
    });
  } else {
    document.getElementById('dailyChart').outerHTML = '<div class="empty">아직 데이터가 없어요</div>';
  }

  // 유저 테이블
  if (USERS.length){
    const head = `<table><thead><tr>
      <th>#</th><th>이름</th><th>클릭</th><th>이름변경</th><th>사용한이름</th>
      <th>방문</th><th>활동일</th><th>처음</th><th>마지막</th></tr></thead><tbody>`;
    const body = USERS.map((u,i)=>`<tr>
      <td class="rank">${i+1}</td>
      <td><span class="name">${escapeHtml(u.current_name||'(이름없음)')}</span><br><span class="uid">${u.user_id.slice(0,8)}…</span></td>
      <td class="num">${(u.clicks||0).toLocaleString()}</td>
      <td class="num">${u.name_changes||0}</td>
      <td class="num">${u.distinct_names||0}</td>
      <td class="num">${u.sessions||0}</td>
      <td class="num">${u.active_days||0}</td>
      <td>${u.first_seen||'-'}</td>
      <td>${u.last_seen||'-'}</td>
    </tr>`).join('');
    document.getElementById('tableWrap').innerHTML = head + body + '</tbody></table>';
  } else {
    document.getElementById('tableWrap').innerHTML = '<div class="empty">아직 데이터가 없어요</div>';
  }

  function escapeHtml(s){ return String(s).replace(/[&<>"']/g, m =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m])); }
</script>
</body>
</html>
"""


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(key: str = ""):
    # 보호키가 설정돼 있는데 틀리면 안내 페이지
    secret = os.environ.get("ANALYTICS_SECRET")
    if secret and key != secret:
        return HTMLResponse("<h2 style='font-family:sans-serif'>🔒 키가 필요합니다: /dashboard?key=...</h2>",
                            status_code=403)
    daily = _daily_data()
    users = _users_data()
    html = (_DASHBOARD_HTML
            .replace("/*DAILY_JSON*/", json.dumps(daily, ensure_ascii=False))
            .replace("/*USERS_JSON*/", json.dumps(users, ensure_ascii=False)))
    return HTMLResponse(html)

# ============================ 분석 모듈 끝 ============================
# ── 서버 실행 ──
# 로컬: python server_deploy.py → 8000번 포트 (DATABASE_URL 환경변수 필요)
# 배포(Render): Render가 PORT 환경변수로 포트를 정해줌 → 그걸 받아서 사용
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    print(f"🐱 팝캣 FastAPI 서버 시작! (PostgreSQL) - port {port}")
    uvicorn.run("server_deploy:app", host="0.0.0.0", port=port)
