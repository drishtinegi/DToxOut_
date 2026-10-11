# DToxOut Regulatory Data & Knowledge-Base Expansion Guide

This guide documents the architecture, data structures, ingestion pipeline, verification workflow, and compliance rules for the DToxOut Verified Regulatory Knowledge Base (Phase 7).

---

## 1. Approved Official Data Sources

All regulatory records in DToxOut must originate from verified official public domain databases or government regulatory bodies. Unverified external scrapers, third-party blogs, or unvetted commercial lists are prohibited.

Approved sources include:
- **European Union**: EU CosIng (Cosmetic Ingredients Database), Official Journal of the European Union (Regulation EC No 1223/2009 Annexes II–VI).
- **United States**: U.S. FDA Voluntary Cosmetic Registration Program (VCRP), FDA OTC Monograph Regulations (21 CFR Parts 330–358), FDA Color Additive Status List.
- **Canada**: Health Canada Cosmetic Ingredient Hotlist.
- **ASEAN**: ASEAN Cosmetic Directive (ACD) Annexes.

---

## 2. Manifest Requirements

Every regulatory import batch MUST include a complete manifest metadata payload. Imports lacking a manifest will be rejected before any processing occurs.

### Required Manifest Fields:
| Field Name | Type | Description |
| :--- | :--- | :--- |
| `sourceOrganization` | String | Official organization publishing the data (e.g. `"European Commission"`). |
| `sourceUrl` | String | Public URL of the source database or official gazette (`http://`, `https://`, or `file://`). |
| `retrievedDate` | ISO Date | Timestamp when the dataset snapshot was downloaded (e.g. `"2026-09-01T00:00:00Z"`). |
| `defaultSourceType` | String | Enum: `REGULATORY_LIST`, `SCIENTIFIC_STUDY`, `VENDOR_SPEC`, `COMMUNITY_REPORT`, `INTERNAL_AUDIT`. |
| `defaultVerificationStatus` | String | Enum: `UNVERIFIED`, `PENDING_REVIEW`, `VERIFIED`, `DEPRECATED`. |
| `licenseNote` | String | Statement confirming data usage compliance and copyright/licensing terms. |

---

## 3. Import Formats (JSON & CSV)

The import engine (`RegulationImportService`) supports JSON and CSV file inputs.

### JSON Format Example (with embedded manifest):
```json
{
  "manifest": {
    "sourceOrganization": "European Commission",
    "sourceUrl": "https://ec.europa.eu/growth/tools-databases/cosing/",
    "retrievedDate": "2026-09-01T00:00:00Z",
    "defaultSourceType": "REGULATORY_LIST",
    "defaultVerificationStatus": "PENDING_REVIEW",
    "licenseNote": "Public sector regulatory database fixture for DToxOut."
  },
  "data": [
    {
      "inciName": "METHYLPARABEN",
      "country": "EU",
      "jurisdiction": "EU",
      "regulatoryStatus": "RESTRICTED",
      "restrictionDetails": "Maximum concentration 0.4% (as acid) for single ester, 0.8% for mixtures.",
      "productCategory": "Cosmetics",
      "concentrationLimit": "0.4%",
      "effectiveDate": "2024-01-01",
      "verificationStatus": "PENDING_REVIEW"
    }
  ]
}
```

### CSV Format Example:
```csv
inciName,country,jurisdiction,regulatoryStatus,restrictionDetails,productCategory,concentrationLimit,effectiveDate,verificationStatus
METHYLPARABEN,EU,EU,RESTRICTED,Maximum concentration 0.4%,Cosmetics,0.4%,2024-01-01,PENDING_REVIEW
```
*(When using CSV, the manifest must be supplied separately via `--manifest manifest.json`)*.

---

## 4. Import CLI Usage & Dry-Run Mode

Run the import script using Python CLI:

### Dry-Run Mode (Preview changes without writing to DB):
```bash
python scripts/import_regulations.py --file data/regulations_batch.json --dry-run
```

### Production Execution (JSON):
```bash
python scripts/import_regulations.py --file data/regulations_batch.json
```

### Production Execution (CSV with separate manifest):
```bash
python scripts/import_regulations.py --file data/regulations_batch.csv --manifest data/manifest.json
```

### Command Options:
- `--file`: Path to JSON or CSV input file (required).
- `--manifest`: Path to separate JSON manifest file.
- `--format`: Force format (`json` or `csv`). Auto-detected by default.
- `--dry-run`: Performs validation, INCI resolution, and idempotency checks without DB mutation.

---

## 5. Data Validation & Matching Rules

1. **INCI Exact Matching**:
   - Every row's `inciName` is matched against canonical `Ingredient.inciName` and `IngredientAlias.alias` (case-insensitive, trimmed).
   - **CRITICAL**: The import service NEVER automatically creates an `Ingredient` record from an unrecognized regulatory name.
   - Unmatched INCI names are collected into `unmatched_names` and logged for expert manual review.

2. **Enum Validation**:
   - `regulatoryStatus`: Must be one of `APPROVED`, `RESTRICTED`, `BANNED`, `PENDING_REVIEW`.
   - `verificationStatus`: Must be one of `UNVERIFIED`, `PENDING_REVIEW`, `VERIFIED`, `DEPRECATED`.
   - `defaultSourceType`: Must be a valid `SourceType` enum value.

3. **Idempotency**:
   - Duplicate entries for `(ingredientId, country, jurisdiction, productCategory)` are checked automatically.
   - Identical records are skipped (`skipped_count`).
   - Modified records are updated (`updated_count`).
   - New records are created (`created_count`).

---

## 6. Review & Verification Workflow

1. All incoming imported records default to `verificationStatus: "PENDING_REVIEW"` or `"UNVERIFIED"`.
2. Domain experts review logged `unmatched_names` and manually map them to canonical INCI entries or add new reviewed `Ingredient` records via admin tools.
3. Upon secondary audit against official gazettes, records are updated to `verificationStatus: "VERIFIED"`.

---

## 7. Jurisdiction Behavior & Risk Policy

- **Score Isolation**: Regulatory disposition in an external jurisdiction is kept separate from the baseline numerical INCI safety score (`0.0–10.0`). An ingredient is NOT labeled "toxic" merely because it is restricted in another region.
- **Selected Jurisdiction Param**: API callers can specify `selected_jurisdiction` (e.g. `"EU"`, `"US"`).
- **Warning Rules**:
  - `BANNED`: Generates a `HIGH` severity `REGULATORY` warning and updates recommendation to `AVOID`.
  - `RESTRICTED`: Generates a `MODERATE` severity `REGULATORY` warning detailing concentration limits and usage conditions.
  - `APPROVED`: Displays source and jurisdiction details.
  - `PENDING_REVIEW`: Displays a `LOW` severity notice stating verification is incomplete.
  - No Record: Displays `"No regulatory record found."`

---

## 8. Update Frequency & Limitations

- **Update Cadence**: Quarterly audit against official regulatory publications (CosIng, FDA notices).
- **Limitations**: Regulations vary by specific product category (rinse-off vs. leave-on, oral care vs. facial cosmetics) and maximum concentration. DToxOut reports jurisdiction-level restrictions but recommends checking finished product context.
