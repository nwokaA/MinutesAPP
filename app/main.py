import os
import re
import json
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta, date
from io import BytesIO

from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import text

# third-party helpers for file parsing
import pdfplumber
import docx2txt

from .db import SessionLocal
from .models import Project, Meeting, Minutes, Item

import ollama  # local LLM & embeddings via Ollama

# --------- Config ----------
EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")  # 768-dim
LLM_MODEL   = os.getenv("OLLAMA_LLM_MODEL", "gemma3:4b")           # lighter default
LLM_OPTIONS = {"temperature": 0.2, "num_ctx": 1024}                # friendly on RAM

app = FastAPI()

# --------- Prompts ----------
SYSTEM_PROMPT = """You are an information extractor for meeting minutes.
Return ONLY JSON with keys: decisions, actions, accomplishments, risks, issues.
Each item should include:
- title (short), detail (1-3 sentences), owner (string or empty)
- due_date (YYYY-MM-DD or empty) for actions; date for decisions/accomplishments
- severity 1..5 for risk/issue (optional), priority 1..5 for action (optional)
- evidence_span: {"start": int, "end": int} (use -1 if unknown)
- confidence: float in [0,1]
Output compact JSON. No prose.
"""

PLAN_PROMPT = """You are a project program lead. Generate a concise, actionable plan for the next 7 days.
Be specific and pragmatic. Use the inputs below.

PROFILE (preferences/tone):
{profile}

CONTEXT (open/overdue actions, risks/issues, recent decisions/accomplishments):
{context}

Return a short bulleted plan with owners and due dates when possible. Keep it tight (5–8 bullets).
"""

# --------- Helpers ----------
def try_parse_json(s: str) -> Dict[str, Any]:
    s = s.strip()
    s = re.sub(r"^```(json)?", "", s, flags=re.IGNORECASE).strip()
    s = re.sub(r"```$", "", s).strip()
    try:
        return json.loads(s)
    except Exception:
        pass
    m = re.search(r"\{.*\}", s, flags=re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return {"decisions": [], "actions": [], "accomplishments": [], "risks": [], "issues": []}

def embed(text_input: str) -> List[float]:
    resp = ollama.embeddings(model=EMBED_MODEL, prompt=text_input)
    return resp["embedding"]

def extract_llm(text_input: str) -> Dict[str, Any]:
    prompt = f"{SYSTEM_PROMPT}\n\nTEXT:\n{text_input}\n\nJSON:"
    out = ollama.generate(model=LLM_MODEL, prompt=prompt, options=LLM_OPTIONS)
    return try_parse_json(out["response"])

def clean_date(val: Optional[str]) -> Optional[str]:
    if not val:
        return None
    val = str(val).strip()
    if val == "":
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", val):
        return val
    return None

def norm_text(x):
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return str(x)
    if isinstance(x, (list, tuple)):
        return ", ".join(str(v) for v in x if str(v).strip())
    if isinstance(x, dict):
        if len(x) <= 3:
            parts = []
            for k, v in x.items():
                if isinstance(v, bool) and v is True:
                    parts.append(str(k))
                else:
                    parts.append(f"{k}: {v}")
            return ", ".join(parts) if parts else None
        return json.dumps(x, ensure_ascii=False)
    s = str(x).strip()
    return s or None

def norm_int(x):
    if x in (None, "", [], {}):
        return None
    try:
        i = int(x)
        return i if i != 0 else None
    except Exception:
        return None

def extract_text_from_file(upload: UploadFile) -> str:
    """Read PDF/DOCX/TXT into a single text string."""
    name = (upload.filename or "").lower()
    content = upload.file.read()
    upload.file.seek(0)

    if name.endswith(".pdf") or upload.content_type == "application/pdf":
        txt_parts = []
        with pdfplumber.open(BytesIO(content)) as pdf:
            for page in pdf.pages:
                t = page.extract_text() or ""
                if t.strip():
                    txt_parts.append(t)
        return "\n\n".join(txt_parts).strip()

    if name.endswith(".docx") or upload.content_type in (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ):
        return (docx2txt.process(BytesIO(content)) or "").strip()

    if upload.content_type in ("text/plain", "text/markdown") or name.endswith((".txt", ".md")):
        try:
            return content.decode("utf-8", errors="ignore")
        except Exception:
            return ""

    # Fallback attempt
    try:
        return content.decode("utf-8", errors="ignore")
    except Exception:
        return ""

# --------- API models ----------
class IngestPayload(BaseModel):
    project_name: str
    meeting_title: str
    raw_text: str
    source_url: Optional[str] = None

# --------- Routes ----------
@app.get("/")
def root():
    return {"msg": "API running locally with Ollama. Use /app (UI) or /ingest, /search, /summary, /items, /reembed"}

# --- Simple HTML Upload UI ---
@app.get("/app", response_class=HTMLResponse)
def app_home():
    return """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Minutes Uploader</title>
  <style>
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial; padding: 32px; max-width: 880px; margin: auto; }
    .card { border: 1px solid #ddd; border-radius: 12px; padding: 24px; box-shadow: 0 2px 10px rgba(0,0,0,.05); }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .muted { color:#666; font-size: 12px; margin-top:6px;}
    button { padding: 10px 16px; border-radius: 10px; border: 0; background: #111827; color: #fff; cursor: pointer;}
    input[type="text"], input[type="file"] { width:100%; padding: 10px; border:1px solid #ccc; border-radius:10px;}
    h1 { margin-bottom: 8px; } h2 { margin: 24px 0 8px; }
  </style>
</head>
<body>
  <h1>Minutes Uploader</h1>
  <p class="muted">Upload a PDF / DOCX / TXT of meeting minutes. We’ll extract Decisions, Actions, Risks, Issues, and Accomplishments and save them.</p>
  <div class="card">
    <form action="/upload" method="post" enctype="multipart/form-data">
      <div class="row">
        <div>
          <label>Project Name</label><br/>
          <input type="text" name="project_name" placeholder="e.g., P1 – ForeSITE" required />
        </div>
        <div>
          <label>Meeting Title</label><br/>
          <input type="text" name="meeting_title" placeholder="e.g., Weekly sync 2025-09-18" required />
        </div>
      </div>
      <div style="margin:12px 0;">
        <label>Minutes File</label><br/>
        <input type="file" name="file" accept=".pdf,.docx,.txt,.md" required />
      </div>
      <button type="submit">Upload & Extract</button>
    </form>
  </div>
  <p class="muted" style="margin-top:12px;">Tip: Results are stored; you can also hit <b>/items</b>, <b>/search</b>, or <b>/summary</b> REST endpoints.</p>
</body>
</html>
    """

@app.post("/upload", response_class=HTMLResponse)
async def upload_minutes(
    project_name: str = Form(...),
    meeting_title: str = Form(...),
    file: UploadFile = File(...)
):
    try:
        # IMPORTANT: don't shadow sqlalchemy.text
        doc_text = extract_text_from_file(file)
        if not doc_text or len(doc_text.strip()) < 10:
            return HTMLResponse(
                f"<p>Could not read any text from <b>{file.filename}</b>. Please upload a PDF, DOCX, or TXT with readable text.</p>",
                status_code=400
            )

        s = SessionLocal()
        try:
            proj = s.query(Project).filter_by(name=project_name).first()
            if not proj:
                proj = Project(name=project_name)
                s.add(proj); s.flush()

            mtg = Meeting(project_id=proj.id, title=meeting_title)
            s.add(mtg); s.flush()

            mins = Minutes(meeting_id=mtg.id, source_url=file.filename, raw_text=doc_text)
            s.add(mins); s.flush()

            vec = embed(doc_text)
            s.execute(text("UPDATE minutes SET embedding = (:v)::vector WHERE id = :id"),
                      {"v": vec, "id": mins.id})

            data = extract_llm(doc_text)

            def ins(items, typ):
                for it in items or []:
                    ev = it.get("evidence_span") or {}
                    s.add(Item(
                        minutes_id=mins.id,
                        project_id=proj.id,
                        type=typ,
                        title=norm_text(it.get("title")),
                        detail=norm_text(it.get("detail")),
                        owner=norm_text(it.get("owner")),
                        due_date=clean_date(it.get("due_date") or it.get("date")),
                        priority=norm_int(it.get("priority")),
                        severity=norm_int(it.get("severity")),
                        evidence_start=ev.get("start", None),
                        evidence_end=ev.get("end", None),
                        confidence=it.get("confidence"),
                    ))

            ins(data.get("decisions"), "decision")
            ins(data.get("actions"), "action")
            ins(data.get("accomplishments"), "accomplishment")
            ins(data.get("risks"), "risk")
            ins(data.get("issues"), "issue")

            s.commit()

            def section(title, items):
                if not items: return ""
                rows = []
                for i in items:
                    ti = (i.get("title") or "").strip()
                    owner = (i.get("owner") or "").strip()
                    due   = (i.get("due_date") or i.get("date") or "").strip() if isinstance(i, dict) else ""
                    detail= (i.get("detail") or "").strip()
                    meta = " | ".join(v for v in [f"Owner: {owner}" if owner else "", f"Due/Date: {due}" if due else ""] if v)
                    rows.append(f"<li><b>{ti}</b>" + (f" — <i>{meta}</i>" if meta else "") +
                                (f"<br/><span class='muted'>{detail}</span>" if detail else "") +
                                "</li>")
                return f"<h2>{title}</h2><ul>{''.join(rows)}</ul>"

            html = f"""
<!doctype html>
<html><head><meta charset="utf-8"/><title>Upload Result</title>
<style>
body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial; padding:32px; max-width:880px; margin:auto}}
.muted{{color:#666; font-size:12px}}
.card{{border:1px solid #ddd; border-radius:12px; padding:24px; box-shadow:0 2px 10px rgba(0,0,0,.05)}}
h1{{margin-bottom:8px}} h2{{margin:24px 0 8px}}
</style></head>
<body>
  <h1>Parsed Minutes</h1>
  <p class="muted">Saved under <b>{project_name}</b> → <b>{meeting_title}</b>. <a href="/app">Upload another</a></p>
  <div class="card">
    {section("Decisions", data.get("decisions") or [])}
    {section("Actions", data.get("actions") or [])}
    {section("Risks", data.get("risks") or [])}
    {section("Issues", data.get("issues") or [])}
    {section("Accomplishments", data.get("accomplishments") or [])}
  </div>
  <p class="muted" style="margin-top:12px;">minutes_id: {mins.id} | project_id: {proj.id} | meeting_id: {mtg.id}</p>
</body></html>
            """
            return HTMLResponse(html)
        finally:
            s.close()
    except Exception as e:
        raise HTTPException(500, f"/upload failed: {e}")

@app.get("/health/db")
def health_db():
    s = SessionLocal()
    try:
        s.execute(text("SELECT 1"))
        return {"db": "ok"}
    finally:
        s.close()

@app.post("/ingest")
def ingest(p: IngestPayload):
    s = SessionLocal()
    try:
        proj = s.query(Project).filter_by(name=p.project_name).first()
        if not proj:
            proj = Project(name=p.project_name)
            s.add(proj); s.flush()

        mtg = Meeting(project_id=proj.id, title=p.meeting_title)
        s.add(mtg); s.flush()

        mins = Minutes(meeting_id=mtg.id, source_url=p.source_url, raw_text=p.raw_text)
        s.add(mins); s.flush()

        vec = embed(p.raw_text)
        s.execute(text("UPDATE minutes SET embedding = (:v)::vector WHERE id = :id"),
                  {"v": vec, "id": mins.id})

        data = extract_llm(p.raw_text)

        def ins(items, typ):
            for it in items or []:
                ev = it.get("evidence_span") or {}
                s.add(Item(
                    minutes_id=mins.id,
                    project_id=proj.id,
                    type=typ,
                    title=norm_text(it.get("title")),
                    detail=norm_text(it.get("detail")),
                    owner=norm_text(it.get("owner")),
                    due_date=clean_date(it.get("due_date") or it.get("date")),
                    priority=norm_int(it.get("priority")),
                    severity=norm_int(it.get("severity")),
                    evidence_start=ev.get("start", None),
                    evidence_end=ev.get("end", None),
                    confidence=it.get("confidence"),
                ))

        ins(data.get("decisions"), "decision")
        ins(data.get("actions"), "action")
        ins(data.get("accomplishments"), "accomplishment")
        ins(data.get("risks"), "risk")
        ins(data.get("issues"), "issue")

        s.commit()
        return {"ok": True, "project_id": proj.id, "meeting_id": mtg.id, "minutes_id": mins.id}
    except Exception as e:
        s.rollback()
        raise HTTPException(500, str(e))
    finally:
        s.close()

@app.get("/search")
def search(q: str, k: int = 5, project_id: Optional[int] = None):
    s = SessionLocal()
    try:
        qvec = embed(q)
        where = "m.embedding IS NOT NULL"
        params = {"qvec": qvec, "k": k}
        if project_id is not None:
            where += " AND mt.project_id = :pid"
            params["pid"] = project_id

        rows = s.execute(text(f"""
            SELECT
              m.id AS minutes_id,
              mt.project_id AS project_id,
              1 - (m.embedding <=> (:qvec)::vector) AS score
            FROM minutes m
            JOIN meetings mt ON mt.id = m.meeting_id
            WHERE {where}
            ORDER BY m.embedding <=> (:qvec)::vector
            LIMIT :k
        """), params).mappings().all()

        return [
            {"minutes_id": r["minutes_id"], "project_id": r["project_id"], "similarity": float(r["score"])}
            for r in rows
        ]
    except Exception as e:
        raise HTTPException(500, f"/search failed: {e}")
    finally:
        s.close()

@app.get("/items")
def list_items(
    project_id: Optional[int] = Query(None),
    typ: Optional[str] = Query(None, description="decision|action|accomplishment|risk|issue|blocker"),
    status: Optional[str] = Query(None, description="open|in_progress|done"),
    due_before: Optional[str] = Query(None, description="YYYY-MM-DD"),
    due_after: Optional[str] = Query(None, description="YYYY-MM-DD"),
    limit: int = Query(50, ge=1, le=500),
):
    s = SessionLocal()
    try:
        where = []
        params: Dict[str, Any] = {"lim": limit}
        if project_id is not None:
            where.append("i.project_id = :pid"); params["pid"] = project_id
        if typ:
            where.append("i.type = :typ"); params["typ"] = typ
        if status:
            where.append("i.status = :st"); params["st"] = status
        if due_before:
            where.append("i.due_date IS NOT NULL AND i.due_date <= :db"); params["db"] = due_before
        if due_after:
            where.append("i.due_date IS NOT NULL AND i.due_date >= :da"); params["da"] = due_after
        wsql = ("WHERE " + " AND ".join(where)) if where else ""

        rows = s.execute(text(f"""
            SELECT i.id, i.minutes_id, i.project_id, i.type, i.title, i.detail, i.owner,
                   i.due_date, i.status, i.priority, i.severity, i.confidence
            FROM items i
            {wsql}
            ORDER BY i.id DESC
            LIMIT :lim
        """), params).mappings().all()

        out = []
        for r in rows:
            d = dict(r)
            if isinstance(d.get("due_date"), date):
                d["due_date"] = d["due_date"].isoformat()
            out.append(d)
        return out
    except Exception as e:
        raise HTTPException(500, f"/items failed: {e}")
    finally:
        s.close()

@app.get("/summary")
def summary(
    project_id: int = Query(...),
    days: int = Query(7, ge=1, le=60),
    plan: bool = Query(False),
    profile: str = Query("", description="Optional profile text to steer the plan")
):
    s = SessionLocal()
    try:
        since = (datetime.utcnow() - timedelta(days=days))

        rows = s.execute(text("""
            SELECT i.id, i.type, i.title, i.detail, i.owner, i.due_date, i.priority, i.severity,
                   m.ts AS minutes_ts
            FROM items i
            JOIN minutes m ON m.id = i.minutes_id
            JOIN meetings mt ON mt.id = m.meeting_id
            WHERE mt.project_id = :pid
              AND (m.ts IS NULL OR m.ts >= :since)
            ORDER BY i.id DESC
            LIMIT 1000
        """), {"pid": project_id, "since": since}).mappings().all()

        decisions, accomplishments, risks, issues = [], [], [], []
        actions_overdue, actions_due_soon, actions_open = [], [], []
        today = date.today()
        soon_cutoff = today + timedelta(days=7)

        def as_dict(r):
            d = dict(r)
            if isinstance(d.get("due_date"), date):
                d["due_date"] = d["due_date"].isoformat()
            if isinstance(d.get("minutes_ts"), datetime):
                d["minutes_ts"] = d["minutes_ts"].isoformat()
            return d

        for r in rows:
            t = r["type"]
            if t == "decision":
                decisions.append(as_dict(r))
            elif t == "accomplishment":
                accomplishments.append(as_dict(r))
            elif t == "risk":
                risks.append(as_dict(r))
            elif t in ("issue", "blocker"):
                issues.append(as_dict(r))
            elif t == "action":
                dd = r["due_date"]
                if isinstance(dd, date):
                    if dd < today:
                        actions_overdue.append(as_dict(r))
                    elif today <= dd <= soon_cutoff:
                        actions_due_soon.append(as_dict(r))
                    else:
                        actions_open.append(as_dict(r))
                else:
                    actions_open.append(as_dict(r))

        out: Dict[str, Any] = {
            "project_id": project_id,
            "window_days": days,
            "decisions": decisions,
            "accomplishments": accomplishments,
            "risks": risks,
            "issues": issues,
            "actions": {
                "overdue": actions_overdue,
                "due_soon": actions_due_soon,
                "open_other": actions_open
            },
            "stats": {
                "counts": {
                    "decisions": len(decisions),
                    "accomplishments": len(accomplishments),
                    "risks": len(risks),
                    "issues": len(issues),
                    "actions_overdue": len(actions_overdue),
                    "actions_due_soon": len(actions_due_soon),
                    "actions_open_other": len(actions_open),
                }
            }
        }

        if plan:
            ctx_parts = []
            if decisions:
                ctx_parts.append("Decisions:\n" + "\n".join(f"- {d.get('title')}" for d in decisions[:10]))
            if accomplishments:
                ctx_parts.append("Accomplishments:\n" + "\n".join(f"- {a.get('title')}" for a in accomplishments[:10]))
            if actions_overdue or actions_due_soon:
                ao = "\n".join(f"- {a.get('title')} (owner: {a.get('owner')}, due: {a.get('due_date')})"
                               for a in actions_overdue[:10])
                ds = "\n".join(f"- {a.get('title')} (owner: {a.get('owner')}, due: {a.get('due_date')})"
                               for a in actions_due_soon[:10])
                if ao:
                    ctx_parts.append("Overdue Actions:\n" + ao)
                if ds:
                    ctx_parts.append("Due Soon (<=7d):\n" + ds)
            if risks or issues:
                rtxt = "\n".join(f"- {r.get('title')} (sev: {r.get('severity')})" for r in (risks + issues)[:10])
                ctx_parts.append("Risks/Issues:\n" + rtxt)

            context = "\n\n".join(ctx_parts) if ctx_parts else "No significant items in the window."
            plan_prompt = PLAN_PROMPT.format(profile=profile or "standard PM tone", context=context)
            resp = ollama.generate(model=LLM_MODEL, prompt=plan_prompt, options=LLM_OPTIONS)
            out["plan"] = resp.get("response", "").strip()

        return out
    except Exception as e:
        raise HTTPException(500, f"/summary failed: {e}")
    finally:
        s.close()

@app.post("/reembed")
def reembed(project_id: Optional[int] = Query(None)):
    """
    Backfill embeddings for minutes rows where embedding IS NULL.
    Optionally scope to a project_id.
    """
    s = SessionLocal()
    try:
        where = "m.embedding IS NULL"
        params: Dict[str, Any] = {}
        if project_id is not None:
            where += " AND mt.project_id = :pid"
            params["pid"] = project_id

        rows = s.execute(text(f"""
            SELECT m.id, m.raw_text
            FROM minutes m
            JOIN meetings mt ON mt.id = m.meeting_id
            WHERE {where}
            ORDER BY m.id
            LIMIT 5000
        """), params).mappings().all()

        updated = 0
        for r in rows:
            vec = embed(r["raw_text"])
            s.execute(text("UPDATE minutes SET embedding = (:v)::vector WHERE id = :id"),
                      {"v": vec, "id": r["id"]})
            updated += 1

        s.commit()
        return {"updated": updated}
    except Exception as e:
        s.rollback()
        raise HTTPException(500, f"/reembed failed: {e}")
    finally:
        s.close()

# --------- NEW: Projects list (JSON) ----------
@app.get("/projects")
def list_projects():
    s = SessionLocal()
    try:
        rows = s.execute(text("SELECT id, name FROM projects ORDER BY name")).mappings().all()
        return [{"id": r["id"], "name": r["name"]} for r in rows]
    finally:
        s.close()

# --------- NEW: Summary UI (HTML) ----------
@app.get("/summary-ui", response_class=HTMLResponse)
def summary_ui():
    return """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Project Summary</title>
  <style>
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial; padding: 32px; max-width: 980px; margin: auto; }
    .card { border: 1px solid #ddd; border-radius: 12px; padding: 24px; box-shadow: 0 2px 10px rgba(0,0,0,.05); }
    .row { display: grid; grid-template-columns: 2fr 1fr 1fr 1fr; gap: 12px; align-items: end; }
    label { font-weight: 600; font-size: 14px; }
    input, select, textarea { width:100%; padding:10px; border:1px solid #ccc; border-radius:10px; font-size:14px; }
    button { padding: 10px 16px; border-radius: 10px; border: 0; background: #111827; color: #fff; cursor: pointer;}
    h1 { margin-bottom: 8px; } h2 { margin: 24px 0 8px; }
    .muted { color:#666; font-size: 12px; }
    ul { padding-left: 20px; }
    .grid2 { display:grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .count { background:#f6f6ff; border:1px solid #e5e7eb; border-radius:10px; padding:12px; text-align:center; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace; white-space: pre-wrap; }
  </style>
</head>
<body>
  <h1>Project Summary</h1>
  <p class="muted">Pick a project and window. Optionally include an AI-generated plan.</p>

  <div class="card">
    <div class="row">
      <div>
        <label>Project</label><br/>
        <select id="project"></select>
      </div>
      <div>
        <label>Days Back</label><br/>
        <input id="days" type="number" min="1" max="60" value="7"/>
      </div>
      <div>
        <label>Include Plan</label><br/>
        <select id="plan">
          <option value="false">No</option>
          <option value="true" selected>Yes</option>
        </select>
      </div>
      <div>
        <button id="run">Generate Summary</button>
      </div>
    </div>
    <div style="margin-top:12px;">
      <label>Profile (optional)</label>
      <textarea id="profile" rows="2" placeholder="e.g., executive concise tone, highlight risks first"></textarea>
    </div>
  </div>

  <div id="out" style="margin-top:16px;"></div>

<script>
async function loadProjects() {
  const sel = document.getElementById('project');
  sel.innerHTML = '<option>Loading...</option>';
  const res = await fetch('/projects');
  const projects = await res.json();
  if (!projects.length) {
    sel.innerHTML = '<option value="">No projects yet</option>';
    return;
  }
  sel.innerHTML = projects.map(p => `<option value="${p.id}">${p.name} (id ${p.id})</option>`).join('');
}

function section(title, items, mapper) {
  if (!items || !items.length) return '';
  const li = items.map(mapper).join('');
  return `<h2>${title}</h2><ul>${li}</ul>`;
}

function itemLi(i) {
  const title = (i.title || '').replaceAll('<','&lt;');
  const owner = (i.owner || '').replaceAll('<','&lt;');
  const due = (i.due_date || '').replaceAll('<','&lt;');
  const det = (i.detail || '').replaceAll('<','&lt;');
  const meta = [owner ? 'Owner: ' + owner : '', due ? 'Due: ' + due : ''].filter(Boolean).join(' | ');
  return `<li><b>${title}</b>${meta ? ' — <i>'+meta+'</i>' : ''}${det ? '<br/><span class="muted">'+det+'</span>' : ''}</li>`;
}

document.getElementById('run').addEventListener('click', async () => {
  const pid = document.getElementById('project').value;
  const days = document.getElementById('days').value || '7';
  const plan = document.getElementById('plan').value;
  const profile = document.getElementById('profile').value || '';
  if (!pid) { alert('Pick a project'); return; }

  const url = `/summary?project_id=${encodeURIComponent(pid)}&days=${encodeURIComponent(days)}&plan=${encodeURIComponent(plan)}&profile=${encodeURIComponent(profile)}`;
  const out = document.getElementById('out');
  out.innerHTML = '<p class="muted">Running summary…</p>';

  try {
    const res = await fetch(url);
    if (!res.ok) {
      const txt = await res.text();
      out.innerHTML = '<pre class="mono">Error: ' + txt.replaceAll('<','&lt;') + '</pre>';
      return;
    }
    const j = await res.json();

    const counts = j.stats?.counts || {};
    const statHtml = `
      <div class="grid2">
        <div class="count">Decisions<br/><b>${counts.decisions || 0}</b></div>
        <div class="count">Accomplishments<br/><b>${counts.accomplishments || 0}</b></div>
        <div class="count">Risks<br/><b>${counts.risks || 0}</b></div>
        <div class="count">Issues<br/><b>${counts.issues || 0}</b></div>
        <div class="count">Actions Overdue<br/><b>${counts.actions_overdue || 0}</b></div>
        <div class="count">Actions Due Soon<br/><b>${counts.actions_due_soon || 0}</b></div>
      </div>
    `;

    const html = `
      <div class="card">
        <p class="muted">project_id: ${j.project_id} • window_days: ${j.window_days}</p>
        ${statHtml}
        ${section('Decisions', j.decisions, itemLi)}
        ${section('Accomplishments', j.accomplishments, itemLi)}
        ${section('Risks', j.risks, i => {
            const sev = (i.severity ?? '').toString();
            return itemLi({...i, detail: (i.detail || '') + (sev ? ' [sev ' + sev + ']' : '')});
        })}
        ${section('Issues', j.issues, itemLi)}
        ${section('Actions — Overdue', j.actions?.overdue || [], itemLi)}
        ${section('Actions — Due Soon', j.actions?.due_soon || [], itemLi)}
        ${section('Actions — Other Open', j.actions?.open_other || [], itemLi)}
        ${j.plan ? '<h2>Plan (Next 7 Days)</h2><pre class="mono">' + j.plan.replaceAll('<','&lt;') + '</pre>' : ''}
      </div>
    `;
    out.innerHTML = html;
  } catch (e) {
    out.innerHTML = '<pre class="mono">Exception: ' + (e?.toString() || 'unknown') + '</pre>';
  }
});

loadProjects();
</script>
</body>
</html>
    """
