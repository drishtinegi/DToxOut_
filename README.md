# 🧴 DToxOut — Cosmetic Ingredient Safety Analyzer

> Scan or type the ingredient list of any cosmetic product and instantly see which ingredients are risky, why, and what safer choices to look for.

**🌐 Live demo:** [https://d-tox-out.vercel.app](https://d-tox-out.vercel.app)

> ⏳ **Note:** the backend runs on a free hosting plan and goes to sleep when idle. The first request after a quiet period can take **up to a minute** to respond. Please wait and refresh once.

---

## ✨ Features

- 🔍 **Ingredient lookup** – search canonical INCI ingredient names
- 📷 **OCR label scanning** – upload a photo of a product label and extract the ingredient list (Tesseract / PaddleOCR / mock provider)
- ⚠️ **Risk analysis engine** – scores every ingredient by risk level (Low, Moderate, High, Very High) with a confidence rating
- 📜 **Regulatory data** – status per jurisdiction (Approved, Restricted, Banned, Pending Review)
- 🧪 **Scientific references & explanations** – plain-language reasons behind each rating
- 💡 **Recommendations** – safer alternatives and what to avoid
- 👤 **User accounts** – sign up, log in, and keep a **scan history**
- 🛡️ **Admin tools** – manage ingredients, regulations, safety profiles and view a dashboard
- 🔒 **Production-ready security** – JWT auth, rate limiting, CORS allowlist, security headers, non-root Docker image

---

## 🧱 Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 19, TypeScript, Vite, Vitest |
| Backend | FastAPI (Python), Gunicorn + Uvicorn |
| Database | PostgreSQL with Prisma ORM |
| OCR | Tesseract, PaddleOCR or mock (switchable) |
| Storage | Local, AWS S3 or Azure Blob (switchable) |
| DevOps | Docker, Docker Compose, GitHub Actions CI |
| Hosting (demo) | Vercel (frontend), Render (backend), Neon (database) |

---

## 🏗️ Architecture

```
┌────────────┐     HTTPS      ┌──────────────────┐      ┌──────────────┐
│  React SPA │ ─────────────▶ │  FastAPI backend │ ───▶ │  PostgreSQL  │
│  (Vercel)  │ ◀───────────── │     (Render)     │ ◀─── │    (Neon)    │
└────────────┘      JSON      └──────────────────┘      └──────────────┘
                                        │
                                        ▼
                             OCR engine + file storage
```

```
DeToxOut/
├── backend/
│   ├── main.py              # FastAPI app entry point
│   ├── app/
│   │   ├── api/             # Route handlers (auth, scan, search, admin, ...)
│   │   ├── services/        # Business logic, OCR, risk & recommendation engines
│   │   ├── core/            # Settings and configuration
│   │   ├── middleware/      # Rate limiting, request logging
│   │   └── tests/           # Pytest suite
│   ├── prisma/              # Database schema and migrations
│   ├── data/                # Regulatory data batches (CSV / JSON)
│   └── scripts/             # Import and admin helper scripts
├── frontend/
│   ├── src/components/      # UI steps: input, review, analysis, history, auth
│   ├── src/services/api.ts  # API client
│   └── src/test/            # Vitest tests
├── docker-compose.yml       # Local full-stack setup
├── docker-compose.prod.yml  # HTTPS overlay (Caddy)
└── DEPLOYMENT.md
```

---

## 🚀 Quick Start (Docker)

**Requirements:** [Docker Desktop](https://www.docker.com/products/docker-desktop/)

```bash
git clone https://github.com/drishtinegi/DToxOut_.git
cd DToxOut_
docker compose up --build
```

In a second terminal, create the database tables:

```bash
docker compose exec backend prisma migrate deploy
```

Open:

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| API | http://localhost:8000 |
| API docs (Swagger) | http://localhost:8000/docs |
| Health check | http://localhost:8000/health/live |

---

## 🛠️ Local Development (without Docker)

**Requirements:** Python 3.10+, Node.js 20+, PostgreSQL (or a free [Neon](https://neon.com) database)

### Backend

```bash
cd backend
python -m venv venv
# Windows: .\venv\Scripts\activate      macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then edit the values (see below)
prisma generate
prisma migrate deploy
uvicorn main:app --reload
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env        # set VITE_API_URL
npm run dev
```

Frontend runs at http://localhost:5173.

---

## ⚙️ Environment Variables

### Backend (`backend/.env`)

| Variable | Description | Example |
|---|---|---|
| `APP_ENV` | `development` or `production` | `production` |
| `DEBUG` | **Must be `false` in production** | `false` |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:pass@host/db?sslmode=require` |
| `JWT_SECRET_KEY` | Secret for signing tokens (32+ chars) | *(random string)* |
| `CORS_ORIGINS` | Comma-separated allowed frontend URLs | `https://d-tox-out.vercel.app` |
| `OCR_PROVIDER` | `mock`, `tesseract` or `paddle` | `tesseract` |
| `STORAGE_PROVIDER` | `local`, `azure` or `s3` | `local` |
| `PORT` | Server port | `8000` |
| `RUN_MIGRATIONS` | Run `prisma migrate deploy` on container start | `false` |

See `backend/.env.example` for the complete list (rate limits, upload limits, OCR options, etc.).

### Frontend (`frontend/.env`)

| Variable | Description | Example |
|---|---|---|
| `VITE_API_URL` | Backend base URL, ending in `/api/v1` | `https://your-api.onrender.com/api/v1` |

> `VITE_API_URL` is baked in at **build time**. Redeploy the frontend after changing it.

---

## ☁️ Free Deployment Guide

This project runs completely free using:

1. **Neon** – PostgreSQL database
2. **Render** – backend (Docker web service, Free plan)
3. **Vercel** – frontend

**Steps in short:**

1. Create a Neon project and copy the connection strings (direct and pooled).
2. From your computer, create the tables once:
   ```bash
   cd backend
   export DATABASE_URL="<direct neon url>"    # PowerShell: $env:DATABASE_URL="..."
   prisma generate
   prisma migrate deploy
   ```
3. On Render, create a **Web Service** from this repo:
   - Root directory: `backend`, runtime: **Docker**, plan: **Free**
   - Health check path: `/health/live`
   - Set the backend environment variables listed above (`APP_ENV=production`, `DEBUG=false`, `PORT=8000`, `RUN_MIGRATIONS=false`, …)
4. On Vercel, import the repo with root directory `frontend` and set `VITE_API_URL`.
5. Put your Vercel URL into `CORS_ORIGINS` on Render.

For cloud and server deployments with HTTPS, see [DEPLOYMENT.md](DEPLOYMENT.md).

---

## 🧪 Testing

```bash
# Backend
cd backend
pytest app/tests/ --ignore=app/tests/test_http_verification.py -v

# Frontend
cd frontend
npm test

# Production build check
npm run build
```

Tests also run automatically on every push via GitHub Actions.

---

## 📡 API Overview

Interactive docs are available at `/docs` (Swagger UI) on the running backend.

| Area | Endpoints (prefix `/api/v1`) |
|---|---|
| Auth | `/auth/...` – register, login, refresh, current user |
| Search | `/search` – ingredient search |
| Scan | `/scan/...` – analyze ingredient text, upload images for OCR |
| Scan history | `/scans` – list, view, save and delete a user's scans |
| Knowledge | `/knowledge` – ingredient knowledge base |
| Admin | `/admin/...` – ingredients, regulations, safety profiles, references, dashboard |
| Health | `/health/live`, `/health/ready` |

---

## 📥 Importing Regulatory Data

```bash
cd backend
python -m scripts.import_regulations --help
```

Data batches live in `backend/data/`. See [REGULATORY_DATA_GUIDE.md](REGULATORY_DATA_GUIDE.md) for the manifest format and import rules.

Create an admin account with:

```bash
python -m scripts.create_admin
```

---

## 🩺 Troubleshooting

| Problem | Fix |
|---|---|
| Site is very slow on first visit | Free backend is waking up. Wait about a minute and refresh. |
| Sign-up or login fails with a network/CORS error | Check `CORS_ORIGINS` on the backend matches your frontend URL exactly (no trailing slash). |
| Frontend calls the wrong API | Set `VITE_API_URL` and **redeploy** the frontend. |
| `DEBUG must be false in production mode` | Set `DEBUG=false` in the backend environment. |
| `email-validator is not installed` | Make sure `email-validator` is in `requirements.txt`. |
| Database authentication failed | Re-copy the Neon connection string with the correct password. |
| Prisma permission error in Docker | Run `prisma generate` as root before switching to `appuser` in the Dockerfile. |

---

## 🤝 Contributing

1. Fork the repo and create a branch: `git checkout -b feature/my-feature`
2. Make your changes and add tests
3. Run the backend and frontend test suites
4. Open a pull request

---

## ⚠️ Disclaimer

DToxOut is an educational tool. Its ratings are based on available regulatory and scientific data and are **not medical advice**. For skin conditions, allergies or pregnancy, consult a qualified professional.

---

## 👩‍💻 Author

Built by **Drishti Negi** · [GitHub](https://github.com/drishtinegi)