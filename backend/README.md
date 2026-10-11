# DToxOut API

A production-ready FastAPI backend project.

## Project Structure

```
DToxOut/
├── app/
│   ├── api/            # API route handlers
│   ├── core/           # Core configuration
│   ├── database/       # Database setup
│   ├── models/         # Database models
│   ├── schemas/        # Pydantic schemas
│   ├── services/       # Business logic
│   ├── utils/          # Utility functions
│   ├── middleware/      # Custom middleware
│   └── tests/          # Test suite
├── uploads/            # Uploaded files
├── main.py             # Application entry point
├── requirements.txt    # Python dependencies
└── .env.example        # Environment variables template
```

## Setup

1. Create a virtual environment:
   ```bash
   python -m venv venv
   ```

2. Activate the virtual environment:
   ```bash
   # Windows
   venv\Scripts\activate

   # macOS/Linux
   source venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Copy `.env.example` to `.env` and configure your environment variables.

## Running the Application

```bash
uvicorn main:app --reload
```

The API will be available at `http://127.0.0.1:8000`.

- Welcome endpoint: `http://127.0.0.1:8000/`
- Health check: `http://127.0.0.1:8000/health`
- API docs: `http://127.0.0.1:8000/docs`

## Phase 1 Analysis Behavior & Matching Rules

### Matching Hierarchy
DToxOut uses a strict, hierarchical ingredient lookup engine (`IngredientMatcher`) to avoid false positives and eliminate unsafe substring matching:
1. **Exact Normalized INCI Name** (`EXACT_INCI`, confidence `1.0`)
2. **Exact Normalized Alias** (`EXACT_ALIAS`, confidence `1.0`)
3. **Exact Normalized Common Name** (`EXACT_COMMON_NAME`, confidence `1.0`)
4. **Bounded Fuzzy Matching** (`FUZZY`, similarity $\ge 0.85$, bounded length ratio $\ge 0.70$, confidence `0.85–0.99`, `manual_confirmation_recommended: true`)
5. **Unknown Classification** (`UNKNOWN`, confidence `0.0`, short generic terms such as "acid", "oil", "extract" are not matched to partial terms)

### Input Normalization & Deduplication
- Input ingredient strings are lowercased and stripped of harmless punctuation (`,;.\t\n\r`).
- Input ingredient lists are deduplicated up-front while preserving **first-seen display order**.
- Recognized count, unknown count, coverage percentage, overall score, and explanations are computed solely on unique deduplicated entries.

### Unknown Ingredient Safety Policy
- Unknown ingredients lower the overall `confidence_score`.
- If any ingredient is unknown (`unknown_count > 0`), a product cannot receive an unqualified `SAFE` recommendation (capped at `USE WITH CAUTION` with an `INCOMPLETE_COVERAGE` warning).
- If all ingredients are unknown (`recognized_count == 0`), the endpoint returns `overall_score = 0.0`, `overall_risk = VERY_HIGH`, `confidence_score = 0`, `recognition_coverage = 0.0%`, and recommendation `USE WITH CAUTION`.

### Risk Scoring Model & Limitations
- Authoritative model: `ProductRiskEngine` (`app.services.risk_engine.ProductRiskEngine`).
- Per-ingredient composite score: $60\%$ `safety_rating` + $25\%$ `safetyProfile.riskLevel` + $15\%$ `evidence_level`.
- Overall score: arithmetic mean of known ingredient composite scores (0.0 to 10.0 scale).
- Risk level classification:
  - `LOW`: Score $\ge 8.5$
  - `MODERATE`: Score $\ge 6.5$
  - `HIGH`: Score $\ge 4.5$
  - `VERY_HIGH`: Score $< 4.5$

### Regulations & Scientific References
- Regulations preserve jurisdiction specificity (e.g., "Restricted in the European Union"). Ingredients are not generically labeled as "toxic everywhere".
- Scientific references and regulations are loaded strictly from the database without inventing sources.

## Running Tests

- Run Phase 1 focused test suite:
  ```bash
  pytest app/tests/test_phase1_scan_analysis.py -v
  ```

- Run Phase 2 import and OCR preparation test suite:
  ```bash
  pytest app/tests/test_phase2_import_and_ocr.py -v
  ```

- Run full non-network test suite:
  ```bash
  pytest app/tests/ --ignore=app/tests/test_http_verification.py -v
  ```

## Phase 2 Knowledge-Base Expansion, Import & OCR Preparation

### Data Provenance & Metadata Schema
Prisma models (`Ingredient`, `IngredientAlias`, `Regulation`, `ScientificReference`) include provenance tracking fields:
- `sourceOrganization`: Primary organization providing data (e.g. "CIR Expert Panel", "EU Cosmetic Ingredient Database").
- `sourceUrl`: URL to official source publication or regulatory list entry.
- `retrievedDate`: Date source data was ingested.
- `sourceType`: Enum (`REGULATORY_LIST`, `SCIENTIFIC_STUDY`, `VENDOR_SPEC`, `COMMUNITY_REPORT`, `INTERNAL_AUDIT`).
- `verificationStatus`: Enum (`UNVERIFIED`, `PENDING_REVIEW`, `VERIFIED`, `DEPRECATED`).
- `reviewerNotes`: Optional internal audit log notes.

### Verified Batch Import Pipeline (`ImportService`)
- Support batch JSON or CSV input with mandatory `manifest` block.
- Validates URLs, source types, verification statuses, required safety data, and detects duplicate INCI entries.
- CLI script:
  ```bash
  python -m scripts.import_ingredients --file data/ingredients_batch.json --dry-run
  ```
- Supports dry-run validation mode and live idempotent upserts. Returns structured import metrics dict (`total_records`, `created_count`, `updated_count`, `skipped_count`, `error_count`, `errors`, `warnings`).

### OCR Text Preparation Adapter (`POST /api/v1/scan/prepare-text`)
- Preprocesses raw OCR text by stripping headers (`Active Ingredients:`, `Contains:`), resolving hyphenated line breaks (`salicylic-\nacid`), removing percentage concentrations (`5%`), and cleaning noise.
- Reuses `IngredientMatcher` to evaluate candidate terms.
- Computes `parser_confidence` (0–100%) and sets `review_required = true` if confidence is under 75% or unrecognized term ratio is above 40%.
- Returns candidate terms, match details, parser confidence, and review warnings without running product risk evaluation or saving scan records.

## Phase 3 React + TypeScript Web Frontend

### Architecture & Workflows
The DToxOut web frontend is built with React 19, TypeScript, Vite, and Vanilla CSS design tokens. It provides a 3-step manual text-analysis workflow:
1. **Landing & Input Screen**: Accepts product name and multiline ingredient lists (comma, semicolon, or newline separated) with preset examples and validation warnings.
2. **Ingredient Review Screen**: Calls `POST /api/v1/scan/prepare-text`, displays parser confidence, strips headers, categorizes terms (Recognized, Ambiguous, Unknown), and allows users to edit, delete, or add candidate terms before explicit safety analysis execution.
3. **Analysis Results Screen**: Displays overall safety score (0–10), risk level badge, coverage percentage, confidence score, incomplete-analysis warning, recommendation status, expandable ingredient details (allergy, pregnancy, acne, sensitive skin risks, jurisdiction regulations, peer-reviewed scientific references with safe external links `rel="noopener noreferrer"`), and unknown ingredient list.

### Frontend Development & Setup
```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Run development server (runs on http://localhost:5173)
npm run dev

# Run Vitest test suite
npm test

# Build production bundle
npm run build
```

### Environment Variables
Create `.env` or `.env.local` inside `frontend/`:
```env
VITE_API_URL=http://localhost:8000/api/v1
```

## Phase 5 & 6 Production Deployment, Security Hardening & Operations

### Health Probes & Observability
- **Liveness Probe**: `GET /health/live` (confirms FastAPI process is responsive).
- **Readiness Probe**: `GET /health/ready` (verifies active database connectivity; returns 503 Service Unavailable if database is unreachable).
- **Legacy Health Endpoint**: `GET /health` and `GET /health/database`.

### Production Configuration & Fail-Fast Rules
- Set `APP_ENV=production` in `.env`.
- Production mode strictly validates required settings on startup via `validate_production_config()`:
  - Requires explicit, secure `JWT_SECRET_KEY` (rejects default or empty secrets).
  - Requires explicit `DATABASE_URL`.
  - Prohibits wildcard `*` CORS origins when credentials are enabled.

### Docker Containerization & Local Integration
- **Backend Dockerfile**: `backend/Dockerfile` (runs under non-root `appuser`, includes Tesseract OCR engine, curl healthcheck).
- **Frontend Dockerfile**: `frontend/Dockerfile` (multi-stage build with Node 20 builder and Nginx alpine runner).
- **Local Integration Compose**:
  ```powershell
  docker-compose up --build
  ```

### Storage Provider Abstraction
Configurable via `STORAGE_PROVIDER`:
- `local`: Default filesystem storage in `UPLOAD_DIR`.
- `azure`: Azure Blob Storage via `AZURE_STORAGE_CONNECTION_STRING`.
- `s3`: AWS S3 or MinIO storage via `S3_BUCKET_NAME`.

## Medical Disclaimer

> **Important**: DToxOut analysis results are informational only and do not constitute a medical diagnosis or healthcare advice.




