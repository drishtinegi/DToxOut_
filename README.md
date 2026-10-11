# DToxOut — Cosmetic Ingredient Safety Analysis Platform

DToxOut is a production-ready application for cosmetic ingredient safety analysis, canonical INCI lookup, OCR label scanning, regulatory risk evaluation, and user scan history tracking.

---

## Architecture Overview

- **Backend**: FastAPI (Python 3.11), Prisma ORM, PostgreSQL (Neon / Azure Flexible Server).
- **Frontend**: React 19, TypeScript, Vite, Vanilla CSS design tokens.
- **OCR Engine**: BaseOCRProvider abstraction supporting local Tesseract OCR, PaddleOCR, and DevMockOCR.
- **Storage**: Vendor-agnostic storage layer supporting local filesystem, AWS S3, and Azure Blob Storage.
- **Deployment**: Docker, Nginx SPA server, GitHub Actions CI/CD, Azure Container Apps / App Service.

---

## Quick Start (Docker Compose)

```bash
cp .env.example .env        # set POSTGRES_PASSWORD and JWT_SECRET_KEY
docker compose up --build
```

- App: `http://localhost:3000` (API is proxied at `/api/v1`)
- Production with HTTPS: see [DEPLOYMENT.md](DEPLOYMENT.md)

---

## Local Development Setup

### 1. Backend
```powershell
cd backend
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env
prisma generate
uvicorn main:app --reload
```

### 2. Frontend
```powershell
cd frontend
npm install
cp .env.example .env
npm run dev
```

---

## Testing & CI

### Run Backend Pytest Suite
```powershell
cd backend
pytest app/tests/ --ignore=app/tests/test_http_verification.py -v
```

### Run Frontend Vitest Suite
```powershell
cd frontend
npm test
```

### Production Build Verification
```powershell
cd frontend
npm run build
```

---

## Documentation Links

- [REGULATORY_DATA_GUIDE.md](REGULATORY_DATA_GUIDE.md): Verified regulatory data import guide, manifest requirements, CLI usage, and jurisdiction policies (Phase 7).
- [DEPLOYMENT.md](DEPLOYMENT.md): Detailed Azure Container Apps deployment guide, scaling, and database operations.
- [backend/README.md](backend/README.md): Backend API, matching hierarchy, and configuration documentation.
- [frontend/README.md](frontend/README.md): Frontend setup, components, and Vitest test suite documentation.
