# SmartTender AI

SmartTender AI is a local MVP for intelligent tender analysis, expert retrieval, and shortlist report generation.

## Challenge scope
- Tender parsing
- Semantic and lexical CV matching
- DOCX shortlist generation
- Local-first demo workflow

## Main deliverable
The challenge-ready application is located in `Backend/LocalMVP`.

## Run locally
```powershell
cd Backend\LocalMVP
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app:app --reload --host 0.0.0.0 --port 8080
```

Open `http://localhost:8080`.

## Notes
- CVs are loaded from the local repository in `Backend/LocalMVP/data/cv_bank`
- sample tenders are available in `Backend/LocalMVP/data/tender_bank`
- secrets must be provided through `.env` and are not committed
