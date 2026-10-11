export interface User {
  id: string;
  email: string;
  username: string;
  role: 'USER' | 'ADMIN';
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user?: User;
}

export interface OCRMatchDetail {
  candidate_term: string;
  match_type: 'EXACT_INCI' | 'EXACT_ALIAS' | 'EXACT_COMMON_NAME' | 'FUZZY' | 'UNKNOWN';
  matched_inci?: string | null;
  confidence_score: number;
  manual_confirmation_recommended: boolean;
  reason: string;
}

export interface OCRPrepareResponse {
  raw_text: string;
  cleaned_text: string;
  candidate_terms: string[];
  match_details: OCRMatchDetail[];
  parser_confidence: number;
  review_required: boolean;
  warnings: string[];
  candidate_count: number;
  recognized_count: number;
  unknown_count: number;
}

export interface Regulation {
  id?: string;
  country: string;
  jurisdiction?: string | null;
  regulatoryStatus?: string;
  restrictionDetails: string;
  source: string;
  sourceOrganization?: string | null;
  sourceUrl?: string | null;
}

export interface ScientificReference {
  id?: string;
  title: string;
  organization: string;
  publicationYear?: number;
  evidenceSummary: string;
  sourceUrl: string;
}

export interface IngredientAnalysis {
  inci_name: string;
  common_name?: string | null;
  description: string;
  function: string;
  safety_rating: number;
  evidence_level: 'LOW' | 'MODERATE' | 'HIGH' | 'VERY_HIGH';
  risk: 'LOW' | 'MODERATE' | 'HIGH' | 'VERY_HIGH';
  original_detected_input?: string;
  match_type?: string;
  match_confidence?: number;
  manual_confirmation_recommended?: boolean;
  regulations?: Regulation[];
  scientific_references?: ScientificReference[];
  allergy_risk?: string;
  pregnancy_risk?: string;
  acne_risk?: string;
  sensitive_skin_risk?: string;
  explanation?: string;
}

export interface UnknownIngredient {
  original_name: string;
  status: string;
  reason: string;
}

export interface RecommendationWarning {
  type: string;
  title: string;
  message: string;
}

export interface ScanRecommendation {
  status: 'SAFE' | 'USE WITH CAUTION' | 'HIGH RISK' | 'AVOID';
  summary: string;
  warnings: RecommendationWarning[];
}

export interface ScanResponse {
  id?: string;
  overall_score: number;
  overall_risk: 'LOW' | 'MODERATE' | 'HIGH' | 'VERY_HIGH';
  confidence_score: number;
  recognition_coverage: number;
  recommendation: ScanRecommendation;
  disclaimer: string;
  recognized_ingredients: IngredientAnalysis[];
  unknown_ingredients: UnknownIngredient[];
  summary_text?: string;
  explanation_reasons?: string[];
  recommended_for?: string[];
  precautions?: string[];
  usage_guidance?: string;
  ingredient_explanations?: Array<{
    ingredient_name: string;
    safety_rating: number;
    risk_level: string;
    reason: string;
  }>;
}

export interface ImageUploadResponse {
  upload_id: string;
  safe_filename: string;
  media_type: string;
  file_size: number;
  status: string;
}

export interface ImageProcessResponse {
  upload_id: string;
  raw_text: string;
  cleaned_text: string;
  candidate_terms: string[];
  match_details: OCRMatchDetail[];
  ocr_provider: string;
  ocr_confidence: number;
  parser_confidence: number;
  processing_duration_ms: number;
  review_required: boolean;
  warnings: string[];
  recognized_count: number;
  unknown_count: number;
}

export interface ScanHistoryItem {
  id: string;
  product_name?: string | null;
  overall_score: number;
  overall_risk: 'LOW' | 'MODERATE' | 'HIGH' | 'VERY_HIGH';
  ingredient_count: number;
  created_at: string;
  createdAt?: string;
}

export interface ScanHistoryDetail extends ScanHistoryItem {
  ingredients: string[];
  analysis_response?: ScanResponse;
}
