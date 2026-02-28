import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import (
    CHROMA_DIR,
    CV_BANK_DIR,
    DB_PATH,
    GEMINI_MODEL,
    OPTIONAL_KEYS,
    OPENROUTER_MODEL,
    PARSED_CVS_DIR,
    PARSED_TENDERS_DIR,
    REPORTS_DIR,
    SEARCH_TOP_K,
    STATIC_DIR,
    TEMPLATES_DIR,
    TENDER_BANK_DIR,
    UPLOADS_DIR,
    DATA_DIR,
)
from database import LocalDatabase
from llm_client import LLMHelper
from parsing import (
    build_cv_search_text,
    build_tender_search_text,
    extract_text,
    file_sha256,
    parse_cv_text,
    parse_tender_text,
    slugify,
    write_json,
)
from reporting import generate_report
from semantic_store import SemanticStore


app = FastAPI(title="SmartTender AI Local MVP", version="0.2.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/artifacts", StaticFiles(directory=str(DATA_DIR)), name="artifacts")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

db = LocalDatabase(DB_PATH)
semantic_store = SemanticStore(str(CHROMA_DIR))
llm_helper = LLMHelper(
    openrouter_api_key=OPTIONAL_KEYS.get("OPENROUTER_API_KEY", ""),
    openrouter_model=OPENROUTER_MODEL,
    gemini_api_key=OPTIONAL_KEYS.get("GEMINI_API_KEY", "") or OPTIONAL_KEYS.get("GOOGLE_API_KEY", ""),
    gemini_model=GEMINI_MODEL,
)


def save_upload(upload: UploadFile, target_dir: Path) -> Path:
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    safe_name = slugify(Path(upload.filename or "upload").stem)
    suffix = Path(upload.filename or "").suffix.lower() or ".txt"
    target_path = target_dir / f"{timestamp}-{safe_name}{suffix}"
    content = upload.file.read()
    target_path.write_bytes(content)
    return target_path


def load_bank_files(directory: Path) -> list[Path]:
    supported = {".pdf", ".txt", ".md"}
    return sorted(
        path for path in directory.iterdir() if path.is_file() and path.suffix.lower() in supported
    )


def to_artifact_path(value: str | Path) -> str:
    path = Path(value)
    try:
        return path.relative_to(DATA_DIR).as_posix()
    except ValueError:
        return path.as_posix()


def education_rank(level: str) -> int:
    order = {"": 0, "bachelor": 1, "master": 2, "phd": 3}
    return order.get(level, 0)


def semantic_distance_to_score(distance: float | None) -> float:
    if distance is None:
        return 0.0
    clipped = min(max(distance, 0.0), 1.0)
    return round((1.0 - clipped) * 100, 2)


def build_justification(
    matched_skills: list[str],
    missing_skills: list[str],
    cv_languages: list[str],
    tender_languages: list[str],
    cv_experience: int,
    tender_experience: int,
    semantic_score: float,
) -> list[str]:
    notes = [f"Semantic similarity score: {semantic_score}/100"]
    if matched_skills:
        notes.append(f"Skills matched: {', '.join(matched_skills[:6])}")
    if missing_skills:
        notes.append(f"Missing skills: {', '.join(missing_skills[:5])}")
    if tender_languages:
        common_languages = sorted(set(cv_languages) & set(tender_languages))
        if common_languages:
            notes.append(f"Languages aligned: {', '.join(common_languages)}")
    if tender_experience:
        notes.append(
            f"Experience: candidate {cv_experience} years vs requirement {tender_experience}"
        )
    return notes


def compute_lexical_score(tender_json: dict[str, Any], cv_json: dict[str, Any]) -> dict[str, Any]:
    required_skills = set(tender_json.get("required_skills", []))
    cv_skills = set(cv_json.get("skills_and_interests", {}).get("technical_skills", []))
    matched_skills = sorted(required_skills & cv_skills)
    missing_skills = sorted(required_skills - cv_skills)

    skill_score = (len(matched_skills) / len(required_skills)) * 45 if required_skills else 25

    tender_languages = {
        language.lower() for language in tender_json.get("languages", []) if language
    }
    cv_languages = {
        item.get("name", "").lower()
        for item in cv_json.get("skills_and_interests", {}).get("languages", [])
        if item.get("name")
    }
    language_score = (
        (len(tender_languages & cv_languages) / len(tender_languages)) * 15
        if tender_languages
        else 8
    )

    required_experience = int(tender_json.get("experience_level", 0) or 0)
    candidate_experience = int(cv_json.get("metadata", {}).get("experience_years", 0) or 0)
    if required_experience:
        experience_ratio = min(candidate_experience / required_experience, 1.0)
        experience_score = experience_ratio * 15
    else:
        experience_score = 8

    required_education = education_rank(tender_json.get("education_level", ""))
    candidate_education = education_rank(cv_json.get("metadata", {}).get("education_level", ""))
    if required_education:
        education_score = 10 if candidate_education >= required_education else 4
    else:
        education_score = 6

    lexical_score = round(skill_score + language_score + experience_score + education_score, 2)
    return {
        "lexical_score": lexical_score,
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "candidate_languages": sorted(cv_languages),
        "candidate_experience_years": candidate_experience,
        "tender_languages": sorted(tender_languages),
        "required_experience": required_experience,
    }


def ingest_cv_file(cv_path: Path) -> dict[str, Any]:
    raw_text = extract_text(cv_path)
    cv_json = parse_cv_text(raw_text, cv_path.name)
    enriched_cv = llm_helper.enrich_cv(raw_text)
    if enriched_cv:
        cv_json["personal_information"]["full_name"] = (
            enriched_cv.get("full_name") or cv_json["personal_information"]["full_name"]
        )
        cv_json["personal_information"]["email"] = (
            enriched_cv.get("email") or cv_json["personal_information"].get("email", "")
        )
        cv_json["personal_information"]["phone"] = (
            enriched_cv.get("phone") or cv_json["personal_information"].get("phone", "")
        )
        cv_json["professional_summary"] = (
            enriched_cv.get("professional_summary") or cv_json.get("professional_summary", "")
        )

        llm_skills = enriched_cv.get("technical_skills") or []
        if llm_skills:
            merged_skills = set(cv_json["skills_and_interests"].get("technical_skills", []))
            merged_skills.update(str(skill).strip().lower() for skill in llm_skills if str(skill).strip())
            cv_json["skills_and_interests"]["technical_skills"] = sorted(merged_skills)

        llm_soft_skills = enriched_cv.get("soft_skills") or []
        if llm_soft_skills:
            merged_soft = set(cv_json["skills_and_interests"].get("soft_skills", []))
            merged_soft.update(str(skill).strip() for skill in llm_soft_skills if str(skill).strip())
            cv_json["skills_and_interests"]["soft_skills"] = sorted(merged_soft)

        llm_languages = enriched_cv.get("languages") or []
        if llm_languages:
            existing = {
                item.get("name", "").lower(): item
                for item in cv_json["skills_and_interests"].get("languages", [])
                if item.get("name")
            }
            for language in llm_languages:
                if str(language).strip():
                    existing[str(language).strip().lower()] = {
                        "name": str(language).strip().title(),
                        "proficiency": None,
                    }
            cv_json["skills_and_interests"]["languages"] = list(existing.values())

        if enriched_cv.get("education_level"):
            cv_json["metadata"]["education_level"] = str(enriched_cv["education_level"]).strip().lower()
        if enriched_cv.get("experience_years") is not None:
            try:
                cv_json["metadata"]["experience_years"] = int(enriched_cv["experience_years"])
            except (TypeError, ValueError):
                pass

    content_hash = file_sha256(cv_path)
    json_path = PARSED_CVS_DIR / f"{slugify(cv_path.stem)}-{content_hash[:8]}.json"
    write_json(cv_json, json_path)
    search_text = build_cv_search_text(cv_json, raw_text)

    row = db.upsert_cv_document(
        {
            "source_name": cv_path.name,
            "file_path": str(cv_path),
            "content_hash": content_hash,
            "json_path": str(json_path),
            "full_name": cv_json["personal_information"]["full_name"],
            "email": cv_json["personal_information"].get("email", ""),
            "phone": cv_json["personal_information"].get("phone", ""),
            "experience_years": cv_json.get("metadata", {}).get("experience_years", 0),
            "education_level": cv_json.get("metadata", {}).get("education_level", ""),
            "search_text": search_text,
        }
    )

    semantic_store.upsert_cv(
        cv_id=row["id"],
        document=search_text,
        metadata={
            "full_name": row["full_name"],
            "source_name": row["source_name"],
            "experience_years": row["experience_years"],
            "education_level": row["education_level"],
        },
    )
    return {"row": row, "cv_json": cv_json}


def sync_cv_bank() -> list[dict[str, Any]]:
    indexed = []
    for cv_path in load_bank_files(CV_BANK_DIR):
        indexed.append(ingest_cv_file(cv_path))
    return indexed


def ingest_tender_file(tender_path: Path) -> dict[str, Any]:
    raw_text = extract_text(tender_path)
    tender_json = parse_tender_text(raw_text, tender_path.name)
    enriched_tender = llm_helper.enrich_tender(raw_text)
    if enriched_tender:
        tender_json["title"] = enriched_tender.get("title") or tender_json["title"]
        tender_json["required_skills"] = enriched_tender.get("required_skills") or tender_json["required_skills"]
        tender_json["preferred_skills"] = enriched_tender.get("preferred_skills") or tender_json["preferred_skills"]
        tender_json["languages"] = enriched_tender.get("languages") or tender_json["languages"]
        tender_json["experience_level"] = enriched_tender.get("experience_level") or tender_json["experience_level"]
        tender_json["education_level"] = enriched_tender.get("education_level") or tender_json["education_level"]
        tender_json["summary"] = enriched_tender.get("summary") or tender_json["summary"]
    content_hash = file_sha256(tender_path)
    json_path = PARSED_TENDERS_DIR / f"{slugify(tender_path.stem)}-{content_hash[:8]}.json"
    write_json(tender_json, json_path)
    search_text = build_tender_search_text(tender_json, raw_text)

    row = db.insert_tender_document(
        {
            "source_name": tender_path.name,
            "file_path": str(tender_path),
            "content_hash": content_hash,
            "json_path": str(json_path),
            "title": tender_json["title"],
            "search_text": search_text,
            "required_skills": tender_json.get("required_skills", []),
        }
    )
    return {"row": row, "tender_json": tender_json, "search_text": search_text}


def search_candidates(tender_json: dict[str, Any], tender_search_text: str) -> list[dict[str, Any]]:
    cv_rows = {row["id"]: row for row in db.list_cv_documents()}
    if not cv_rows:
        return []

    query = semantic_store.search(tender_search_text, limit=max(SEARCH_TOP_K, len(cv_rows)))
    semantic_hits = {}
    ids = query.get("ids", [[]])[0]
    distances = query.get("distances", [[]])[0]
    for idx, hit_id in enumerate(ids):
        semantic_hits[int(hit_id)] = distances[idx] if idx < len(distances) else None

    ranking = []
    for cv_id, row in cv_rows.items():
        cv_json = json.loads(Path(row["json_path"]).read_text(encoding="utf-8"))
        lexical = compute_lexical_score(tender_json, cv_json)
        semantic_score = semantic_distance_to_score(semantic_hits.get(cv_id))
        final_score = round((lexical["lexical_score"] * 0.55) + (semantic_score * 0.45), 2)
        llm_notes = llm_helper.explain_match(
            tender_json=tender_json,
            cv_json=cv_json,
            lexical_score=lexical["lexical_score"],
            semantic_score=semantic_score,
            final_score=final_score,
        )
        ranking.append(
            {
                "cv_id": cv_id,
                "candidate_name": row["full_name"],
                "source_file": row["source_name"],
                "score": final_score,
                "semantic_score": semantic_score,
                "lexical_score": lexical["lexical_score"],
                "matched_skills": lexical["matched_skills"],
                "missing_skills": lexical["missing_skills"],
                "candidate_languages": lexical["candidate_languages"],
                "candidate_experience_years": lexical["candidate_experience_years"],
                "justification": llm_notes
                or build_justification(
                    lexical["matched_skills"],
                    lexical["missing_skills"],
                    lexical["candidate_languages"],
                    lexical["tender_languages"],
                    lexical["candidate_experience_years"],
                    lexical["required_experience"],
                    semantic_score,
                ),
            }
        )

    ranking.sort(key=lambda item: item["score"], reverse=True)
    return ranking


def process_pipeline(tender_path: Path, cv_paths: list[Path]) -> dict[str, Any]:
    for cv_path in cv_paths:
        ingest_cv_file(cv_path)

    tender = ingest_tender_file(tender_path)
    ranking = search_candidates(tender["tender_json"], tender["search_text"])
    report_path = generate_report(tender["tender_json"], ranking[:5], REPORTS_DIR)
    report_artifact_path = to_artifact_path(report_path)
    run_id = db.create_match_run(tender["row"]["id"], report_artifact_path)
    db.store_match_results(run_id, ranking)

    return {
        "tender": tender["tender_json"],
        "ranking": ranking,
        "report_path": report_artifact_path,
        "cv_count": db.count_cv_documents(),
        "indexed_cv_count": db.count_cv_documents(),
        "semantic_index_count": semantic_store.count(),
        "run_id": run_id,
    }


def render_home(request: Request, result: dict[str, Any] | None = None, error: str = "") -> HTMLResponse:
    available_cv_bank = [path.name for path in load_bank_files(CV_BANK_DIR)]
    available_tender_bank = [path.name for path in load_bank_files(TENDER_BANK_DIR)]
    context = {
        "request": request,
        "result": result,
        "error": error,
        "available_cv_bank": available_cv_bank,
        "available_tender_bank": available_tender_bank,
        "cv_count": db.count_cv_documents(),
        "semantic_index_count": semantic_store.count(),
        "api_keys_configured": [name for name, value in OPTIONAL_KEYS.items() if value],
    }
    return templates.TemplateResponse("index.html", context)


def render_admin(request: Request) -> HTMLResponse:
    cv_rows = [dict(row) for row in db.list_cv_documents()]
    tender_rows = [dict(row) for row in db.list_tender_documents()]
    run_rows = []
    for row in db.list_recent_match_runs():
        item = dict(row)
        item["report_href"] = to_artifact_path(item["report_path"])
        run_rows.append(item)
    context = {
        "request": request,
        "cv_rows": cv_rows,
        "tender_rows": tender_rows,
        "run_rows": run_rows,
        "cv_count": db.count_cv_documents(),
        "semantic_index_count": semantic_store.count(),
        "api_keys_configured": [name for name, value in OPTIONAL_KEYS.items() if value],
    }
    return templates.TemplateResponse("admin.html", context)


@app.on_event("startup")
async def startup_sync() -> None:
    sync_cv_bank()


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return render_home(request)


@app.get("/demo")
async def demo_redirect() -> RedirectResponse:
    return RedirectResponse(url="/#workspace", status_code=303)


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request) -> HTMLResponse:
    return render_admin(request)


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "mode": "local-semantic-demo",
        "indexed_cv_count": db.count_cv_documents(),
        "semantic_index_count": semantic_store.count(),
        "configured_api_keys": [name for name, value in OPTIONAL_KEYS.items() if value],
    }


@app.get("/api/cvs")
async def list_cvs() -> list[dict[str, Any]]:
    return [dict(row) for row in db.list_cv_documents()]


@app.get("/api/admin/summary")
async def admin_summary() -> dict[str, Any]:
    return {
        "cv_count": db.count_cv_documents(),
        "semantic_index_count": semantic_store.count(),
        "configured_api_keys": [name for name, value in OPTIONAL_KEYS.items() if value],
        "recent_runs": [dict(row) for row in db.list_recent_match_runs()],
        "recent_tenders": [dict(row) for row in db.list_tender_documents()[:10]],
    }


@app.post("/api/index-bank")
async def index_bank() -> dict[str, Any]:
    indexed = sync_cv_bank()
    return {
        "indexed_count": len(indexed),
        "total_cv_count": db.count_cv_documents(),
        "semantic_index_count": semantic_store.count(),
    }


@app.post("/demo", response_class=HTMLResponse)
async def run_demo(
    request: Request,
    tender_file: UploadFile = File(...),
    cv_files: list[UploadFile] = File(default=[]),
) -> HTMLResponse:
    try:
        tender_path = save_upload(tender_file, UPLOADS_DIR)
        uploaded_cv_paths = [save_upload(upload, UPLOADS_DIR) for upload in cv_files if upload.filename]
        result = process_pipeline(tender_path, uploaded_cv_paths)
        result["bank_mode"] = not uploaded_cv_paths
        result["uploaded_count"] = len(uploaded_cv_paths)
        return render_home(request, result=result)
    except Exception as exc:
        return render_home(request, error=f"Pipeline error: {exc}")


@app.post("/api/demo")
async def run_demo_api(
    tender_file: UploadFile = File(...),
    cv_files: list[UploadFile] = File(default=[]),
) -> JSONResponse:
    tender_path = save_upload(tender_file, UPLOADS_DIR)
    uploaded_cv_paths = [save_upload(upload, UPLOADS_DIR) for upload in cv_files if upload.filename]
    result = process_pipeline(tender_path, uploaded_cv_paths)
    result["bank_mode"] = not uploaded_cv_paths
    result["uploaded_count"] = len(uploaded_cv_paths)
    return JSONResponse(content=result)
