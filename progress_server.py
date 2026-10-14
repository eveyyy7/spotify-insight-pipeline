"""Read-only local progress page for the 100k classification run."""

import argparse
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


PAGE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Spotify Insight · 实时进度</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#0b0f0d;color:#f5fff9;font:16px/1.5 system-ui,-apple-system,sans-serif}main{max-width:860px;margin:0 auto;padding:48px 24px}h1{font-size:clamp(30px,6vw,54px);margin:0 0 8px}.sub{color:#91a79b;margin:0 0 36px}.card{background:#121a16;border:1px solid #263b30;border-radius:20px;padding:24px;margin:18px 0}.hero{font-size:clamp(46px,10vw,86px);font-weight:750;letter-spacing:-.05em;color:#1ed760}.bar{height:18px;background:#26302b;border-radius:20px;overflow:hidden;margin:18px 0}.fill{height:100%;background:linear-gradient(90deg,#1ed760,#74f3a5);transition:width .4s}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px}.metric{background:#0d1410;border-radius:14px;padding:16px}.metric b{display:block;font-size:25px}.metric span,.foot{color:#91a79b;font-size:13px}.ok{color:#74f3a5}.warn{color:#ffd166}button{background:#1ed760;color:#07120b;border:0;border-radius:999px;padding:10px 16px;font-weight:700;cursor:pointer}
</style></head><body><main><p class="ok">● LIVE · 本机只读</p><h1>Spotify Insight Pipeline</h1><p class="sub">每 5 秒自动刷新，不显示评论正文或 API 密钥。</p><section class="card"><div class="hero" id="completed">—</div><div>已完成分类</div><div class="bar"><div class="fill" id="fill"></div></div><div id="percent">—</div></section><section class="grid"><div class="metric"><b id="pending">—</b><span>等待处理</span></div><div class="metric"><b id="flight">—</b><span>处理中</span></div><div class="metric"><b id="quarantine">—</b><span>空文本隔离</span></div><div class="metric"><b id="cost">—</b><span>估算成本 / 作业硬上限</span></div><div class="metric"><b id="rate">—</b><span>最近 5 分钟速度</span></div><div class="metric"><b id="eta">—</b><span>预计分类完成</span></div></section><section class="card"><b id="state">正在连接…</b><p class="foot" id="updated"></p><button onclick="load()">立即刷新</button></section></main><script>
const n=x=>Number(x).toLocaleString();async function load(){try{const r=await fetch('/api/progress',{cache:'no-store'});const d=await r.json();completed.textContent=n(d.completed);pending.textContent=n(d.pending);flight.textContent=n(d.in_flight);quarantine.textContent=n(d.quarantined);cost.textContent='$'+d.spent.toFixed(4)+' / $'+d.cap.toFixed(0);rate.textContent=d.rate_per_minute?d.rate_per_minute.toFixed(0)+' 行/分钟':'计算中';eta.textContent=d.eta_utc?new Date(d.eta_utc).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}):'计算中';fill.style.width=d.percent+'%';percent.textContent=d.percent.toFixed(2)+'% of '+n(d.target)+' rows';state.textContent=d.pending===0&&d.in_flight===0?'分类阶段已完成':'任务正在正常运行';state.className=d.pending===0?'ok':'';updated.textContent='数据库更新时间：'+d.database_updated+' · 页面刷新：'+new Date().toLocaleTimeString();}catch(e){state.textContent='暂时无法读取进度';state.className='warn'}}load();setInterval(load,5000);
</script></body></html>"""


def snapshot(db_path, target):
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2)
    try:
        counts = dict(db.execute(
            "SELECT status,COUNT(*) FROM work_queue WHERE source_index < ? GROUP BY status",
            (target,),
        ))
        ledger = db.execute(
            "SELECT spent_estimated_usd,reserved_usd,cap_usd,updated_at FROM spend_ledger WHERE singleton=1"
        ).fetchone()
        recent = db.execute(
            """SELECT COUNT(*),MIN(julianday(updated_at)),MAX(julianday(updated_at))
               FROM work_queue WHERE source_index < ? AND status='completed'
               AND julianday(updated_at) >= julianday('now','-5 minutes')""",
            (target,),
        ).fetchone()
    finally:
        db.close()
    completed = counts.get("completed", 0)
    quarantined = counts.get("quarantined", 0)
    covered = completed + quarantined
    elapsed_minutes = ((recent[2] - recent[1]) * 1440) if recent[0] > 1 else 0
    rate_per_minute = ((recent[0] - 1) / elapsed_minutes) if elapsed_minutes > 0 else None
    remaining = counts.get("pending", 0) + counts.get("in_flight", 0)
    eta = (
        datetime.now(timezone.utc) + timedelta(minutes=remaining / rate_per_minute)
        if rate_per_minute and remaining else None
    )
    return {
        "target": target,
        "completed": completed,
        "pending": counts.get("pending", 0),
        "in_flight": counts.get("in_flight", 0),
        "quarantined": quarantined,
        "failed": counts.get("failed", 0),
        "percent": round(100 * covered / target, 4),
        "spent": float(ledger[0]),
        "reserved": float(ledger[1]),
        "cap": float(ledger[2]),
        "rate_per_minute": round(rate_per_minute, 2) if rate_per_minute else None,
        "eta_utc": eta.isoformat() if eta else None,
        "database_updated": ledger[3],
        "served_at": datetime.now(timezone.utc).isoformat(),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path("grading_full/pipeline_state.sqlite"))
    parser.add_argument("--target", type=int, default=100100)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    db_path = args.db.resolve()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.split("?", 1)[0] == "/api/progress":
                body = json.dumps(snapshot(db_path, args.target)).encode()
                content_type = "application/json"
            elif self.path.split("?", 1)[0] in {"/", "/index.html"}:
                body = PAGE.encode()
                content_type = "text/html; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Progress page: http://127.0.0.1:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
