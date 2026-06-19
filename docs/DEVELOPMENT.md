# Development Guide

## First-time setup

```bash
git clone https://github.com/PrasannaMishra001/astra-ide
cd astra-ide
```

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate     # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev   # http://localhost:3000
```

### Collab server
```bash
cd collab-server
npm install
npm start    # ws://localhost:1234
```

## Running tests

```bash
# ML packages (no extra deps required)
python -m unittest ml.risk_scorer.test_scorer ml.scheduler.test_env ml.prewarming.test_dataset -v

# Frontend type-check
cd frontend && npx tsc --noEmit

# Collab server smoke
cd collab-server && npm start &  curl http://localhost:1234/healthz
```

## Common workflows

### Add a new API endpoint
1. Define request/response schemas in `backend/app/schemas/`
2. Add route in `backend/app/api/<module>.py`
3. Register the router in `backend/app/api/__init__.py`
4. Update `docs/API.md`
5. Add API client method in `frontend/src/lib/api.ts`

### Add a new ML experiment
1. Create `ml/<topic>/<experiment>.py`
2. Use a `--seed` arg for reproducibility
3. Save output to `runs/<topic>/<experiment>/`
4. Add unit tests in `ml/<topic>/test_*.py`

### Make a release
The `docker.yml` workflow auto-builds and pushes to GHCR on every push to `main`.
For a tagged release:
```bash
git tag v0.X.0 && git push --tags
```

## Code conventions

- **Python:** PEP 8, type hints required on public functions.
- **TypeScript:** strict mode on, no `any` in shared code.
- **Commits:** short imperative subject (4-7 words). Body optional.
- **PR titles:** mirror the commit style.
