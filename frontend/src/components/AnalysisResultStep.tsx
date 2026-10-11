import React, { useState } from 'react';
import {
  ShieldAlert,
  ShieldCheck,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  RotateCcw,
  Edit3,
  BookOpen,
  Globe,
  Info,
  CheckCircle,
} from 'lucide-react';
import type { ScanResponse, IngredientAnalysis } from '../types';

interface AnalysisResultStepProps {
  productName: string;
  result: ScanResponse;
  onEdit: () => void;
  onNewAnalysis: () => void;
}

export const AnalysisResultStep: React.FC<AnalysisResultStepProps> = ({
  productName,
  result,
  onEdit,
  onNewAnalysis,
}) => {
  // State for expandable accordion item indices
  const [expandedIndices, setExpandedIndices] = useState<Set<number>>(new Set([0]));

  const toggleExpand = (idx: number) => {
    const next = new Set(expandedIndices);
    if (next.has(idx)) {
      next.delete(idx);
    } else {
      next.add(idx);
    }
    setExpandedIndices(next);
  };

  const getRiskBadgeClass = (risk: string) => {
    switch (risk?.toUpperCase()) {
      case 'LOW':
        return 'badge-low';
      case 'MODERATE':
        return 'badge-moderate';
      case 'HIGH':
      case 'VERY_HIGH':
        return 'badge-high';
      default:
        return 'badge-unknown';
    }
  };

  const getRecommendationBadgeClass = (status: string) => {
    switch (status?.toUpperCase()) {
      case 'SAFE':
        return 'badge-low';
      case 'USE WITH CAUTION':
        return 'badge-moderate';
      case 'HIGH RISK':
      case 'AVOID':
        return 'badge-high';
      default:
        return 'badge-unknown';
    }
  };

  const hasUnknowns = result.unknown_ingredients && result.unknown_ingredients.length > 0;

  return (
    <div className="card animate-fade-in" style={{ maxWidth: '960px', margin: '0 auto' }}>
      {/* Top Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '1.25rem',
          paddingBottom: '1rem',
          borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
        }}
      >
        <div>
          <h2
            style={{
              fontFamily: 'var(--font-heading)',
              fontSize: '1.5rem',
              fontWeight: 700,
              color: '#f8fafc',
            }}
          >
            Ingredient Safety Analysis Results
          </h2>
          {productName && (
            <p style={{ color: '#0ea5e9', fontSize: '0.9375rem', fontWeight: 600 }}>
              Product: {productName}
            </p>
          )}
        </div>

        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button onClick={onEdit} className="btn btn-secondary" style={{ padding: '0.5rem 0.875rem' }}>
            <Edit3 size={16} />
            <span>Edit Ingredients</span>
          </button>
          <button onClick={onNewAnalysis} className="btn btn-primary" style={{ padding: '0.5rem 0.875rem' }}>
            <RotateCcw size={16} />
            <span>New Analysis</span>
          </button>
        </div>
      </div>

      {/* Official Medical Disclaimer Banner */}
      <div className="alert-banner alert-info" style={{ marginBottom: '1.25rem' }}>
        <Info size={20} style={{ flexShrink: 0 }} />
        <div>
          <strong>Informational Notice:</strong> {result.disclaimer || 'DToxOut analysis results are informational only and do not constitute a medical diagnosis or healthcare advice.'}
        </div>
      </div>

      {/* Incomplete Analysis Warning Banner if Unknowns exist */}
      {hasUnknowns && (
        <div className="alert-banner alert-warning" style={{ marginBottom: '1.25rem' }}>
          <AlertTriangle size={20} style={{ flexShrink: 0 }} />
          <div>
            <strong>Incomplete Ingredient Coverage:</strong> {result.unknown_ingredients.length} ingredient(s) could not be identified in the DToxOut database. Recommendation is capped at USE WITH CAUTION because safety cannot be guaranteed for unknown ingredients.
          </div>
        </div>
      )}

      {/* Score Overview Grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: '1rem',
          marginBottom: '1.5rem',
        }}
      >
        {/* Overall Score */}
        <div
          style={{
            background: 'rgba(15, 23, 42, 0.8)',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            borderRadius: '12px',
            padding: '1rem',
            textAlign: 'center',
          }}
        >
          <div style={{ fontSize: '0.75rem', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Safety Score
          </div>
          <div
            style={{
              fontSize: '2rem',
              fontWeight: 800,
              fontFamily: 'var(--font-heading)',
              color: result.overall_score >= 8.5 ? '#34d399' : result.overall_score >= 6.5 ? '#fbbf24' : '#f87171',
              margin: '0.25rem 0',
            }}
          >
            {result.overall_score.toFixed(1)} / 10
          </div>
          <div style={{ fontSize: '0.7rem', color: '#64748b' }}>
            0 = High Concern, 10 = Safest
          </div>
        </div>

        {/* Overall Risk Level */}
        <div
          style={{
            background: 'rgba(15, 23, 42, 0.8)',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            borderRadius: '12px',
            padding: '1rem',
            textAlign: 'center',
          }}
        >
          <div style={{ fontSize: '0.75rem', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Overall Risk
          </div>
          <div style={{ margin: '0.5rem 0' }}>
            <span className={`badge ${getRiskBadgeClass(result.overall_risk)}`} style={{ fontSize: '0.875rem', padding: '0.375rem 0.875rem' }}>
              {result.overall_risk}
            </span>
          </div>
          <div style={{ fontSize: '0.7rem', color: '#64748b' }}>
            Calculated Risk Engine
          </div>
        </div>

        {/* Recognition Coverage */}
        <div
          style={{
            background: 'rgba(15, 23, 42, 0.8)',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            borderRadius: '12px',
            padding: '1rem',
            textAlign: 'center',
          }}
        >
          <div style={{ fontSize: '0.75rem', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Coverage
          </div>
          <div style={{ fontSize: '1.75rem', fontWeight: 800, color: '#38bdf8', margin: '0.25rem 0' }}>
            {result.recognition_coverage?.toFixed(0) ?? 100}%
          </div>
          <div style={{ fontSize: '0.7rem', color: '#64748b' }}>
            Matched Ingredients
          </div>
        </div>

        {/* Confidence Score */}
        <div
          style={{
            background: 'rgba(15, 23, 42, 0.8)',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            borderRadius: '12px',
            padding: '1rem',
            textAlign: 'center',
          }}
        >
          <div style={{ fontSize: '0.75rem', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Confidence
          </div>
          <div style={{ fontSize: '1.75rem', fontWeight: 800, color: '#a5b4fc', margin: '0.25rem 0' }}>
            {result.confidence_score ?? 100}%
          </div>
          <div style={{ fontSize: '0.7rem', color: '#64748b' }}>
            Data Completeness
          </div>
        </div>
      </div>

      {/* Product Recommendation Banner */}
      {result.recommendation && (
        <div
          style={{
            background: 'rgba(30, 41, 59, 0.6)',
            border: '1px solid rgba(255, 255, 255, 0.12)',
            borderRadius: '12px',
            padding: '1.25rem',
            marginBottom: '1.5rem',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
            {result.recommendation.status === 'SAFE' ? (
              <ShieldCheck size={22} color="#34d399" />
            ) : (
              <ShieldAlert size={22} color="#fbbf24" />
            )}
            <span style={{ fontSize: '1rem', fontWeight: 700, color: '#f8fafc' }}>
              Recommendation Status:
            </span>
            <span className={`badge ${getRecommendationBadgeClass(result.recommendation.status)}`}>
              {result.recommendation.status}
            </span>
          </div>

          <p style={{ color: '#cbd5e1', fontSize: '0.9375rem', marginBottom: '0.5rem' }}>
            {result.recommendation.summary || result.summary_text}
          </p>

          {result.recommendation.warnings && result.recommendation.warnings.length > 0 && (
            <div style={{ marginTop: '0.75rem', display: 'flex', flexDirection: 'column', gap: '0.375rem' }}>
              {result.recommendation.warnings.map((w, idx) => (
                <div key={idx} style={{ fontSize: '0.8125rem', color: '#fcd34d', display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
                  <span>⚠️</span>
                  <span><strong>{w.title}:</strong> {w.message}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Recognized Ingredients Accordion List */}
      <div style={{ marginBottom: '1.75rem' }}>
        <h3 style={{ fontSize: '1.125rem', fontWeight: 700, color: '#f8fafc', marginBottom: '1rem' }}>
          Recognized Ingredients ({result.recognized_ingredients?.length || 0}):
        </h3>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {result.recognized_ingredients?.map((ing: IngredientAnalysis, idx: number) => {
            const isExpanded = expandedIndices.has(idx);

            return (
              <div
                key={idx}
                style={{
                  background: 'rgba(15, 23, 42, 0.7)',
                  border: '1px solid rgba(255, 255, 255, 0.08)',
                  borderRadius: '12px',
                  overflow: 'hidden',
                }}
              >
                {/* Accordion Header */}
                <div
                  onClick={() => toggleExpand(idx)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '1rem 1.25rem',
                    cursor: 'pointer',
                    background: isExpanded ? 'rgba(30, 41, 59, 0.5)' : 'transparent',
                    transition: 'background 0.2s ease',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flex: 1 }}>
                    <CheckCircle size={18} color="#34d399" />
                    <div>
                      <div style={{ fontSize: '1rem', fontWeight: 700, color: '#f8fafc' }}>
                        {ing.inci_name}
                        {ing.common_name && (
                          <span style={{ fontSize: '0.875rem', color: '#94a3b8', fontWeight: 400, marginLeft: '0.5rem' }}>
                            ({ing.common_name})
                          </span>
                        )}
                      </div>
                      <div style={{ fontSize: '0.8125rem', color: '#64748b' }}>
                        Function: {ing.function}
                      </div>
                    </div>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontSize: '0.875rem', fontWeight: 700, color: '#0ea5e9' }}>
                        Safety: {ing.safety_rating.toFixed(1)} / 10
                      </div>
                      <div style={{ fontSize: '0.7rem', color: '#64748b' }}>
                        Evidence: {ing.evidence_level}
                      </div>
                    </div>

                    <span className={`badge ${getRiskBadgeClass(ing.risk)}`}>
                      {ing.risk}
                    </span>

                    {isExpanded ? <ChevronUp size={18} color="#94a3b8" /> : <ChevronDown size={18} color="#94a3b8" />}
                  </div>
                </div>

                {/* Accordion Expandable Details */}
                {isExpanded && (
                  <div
                    style={{
                      padding: '1.25rem',
                      borderTop: '1px solid rgba(255, 255, 255, 0.08)',
                      background: 'rgba(15, 23, 42, 0.4)',
                    }}
                  >
                    <p style={{ fontSize: '0.875rem', color: '#cbd5e1', marginBottom: '1rem', lineHeight: 1.6 }}>
                      {ing.description}
                    </p>

                    {/* Match Details */}
                    {ing.match_type && (
                      <div style={{ fontSize: '0.75rem', color: '#94a3b8', marginBottom: '1rem', display: 'flex', gap: '1rem' }}>
                        <span>Match Tier: <strong>{ing.match_type}</strong></span>
                        {ing.match_confidence !== undefined && (
                          <span>Confidence: <strong>{(ing.match_confidence * 100).toFixed(0)}%</strong></span>
                        )}
                      </div>
                    )}

                    {/* Detailed Safety Profile Risks */}
                    {(ing.allergy_risk || ing.pregnancy_risk || ing.acne_risk || ing.sensitive_skin_risk) && (
                      <div
                        style={{
                          display: 'grid',
                          gridTemplateColumns: 'repeat(4, 1fr)',
                          gap: '0.625rem',
                          margin: '1rem 0',
                          padding: '0.75rem',
                          background: 'rgba(30, 41, 59, 0.6)',
                          borderRadius: '8px',
                        }}
                      >
                        <div>
                          <div style={{ fontSize: '0.7rem', color: '#64748b' }}>Allergy Risk</div>
                          <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: '#e2e8f0' }}>{ing.allergy_risk || 'Low'}</div>
                        </div>
                        <div>
                          <div style={{ fontSize: '0.7rem', color: '#64748b' }}>Pregnancy Risk</div>
                          <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: '#e2e8f0' }}>{ing.pregnancy_risk || 'Low'}</div>
                        </div>
                        <div>
                          <div style={{ fontSize: '0.7rem', color: '#64748b' }}>Acne / Comedogenic</div>
                          <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: '#e2e8f0' }}>{ing.acne_risk || 'Low'}</div>
                        </div>
                        <div>
                          <div style={{ fontSize: '0.7rem', color: '#64748b' }}>Sensitive Skin</div>
                          <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: '#e2e8f0' }}>{ing.sensitive_skin_risk || 'Low'}</div>
                        </div>
                      </div>
                    )}

                    {/* Country Specific Regulations */}
                    {ing.regulations && ing.regulations.length > 0 && (
                      <div style={{ marginTop: '1rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.375rem', fontSize: '0.8125rem', fontWeight: 700, color: '#38bdf8', marginBottom: '0.5rem' }}>
                          <Globe size={14} />
                          <span>Regulatory Status by Jurisdiction:</span>
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.375rem' }}>
                          {ing.regulations.map((reg, rIdx) => (
                            <div key={rIdx} style={{ fontSize: '0.8125rem', color: '#cbd5e1', padding: '0.5rem', background: 'rgba(15, 23, 42, 0.5)', borderRadius: '6px' }}>
                              <strong>{reg.jurisdiction || reg.country}:</strong> {reg.regulatoryStatus || 'APPROVED'} — {reg.restrictionDetails}
                              {reg.sourceUrl && (
                                <a
                                  href={reg.sourceUrl}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  style={{ color: '#0ea5e9', marginLeft: '0.5rem', textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: '2px' }}
                                >
                                  Source Link <ExternalLink size={12} />
                                </a>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Peer-Reviewed Scientific References */}
                    {ing.scientific_references && ing.scientific_references.length > 0 && (
                      <div style={{ marginTop: '1rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.375rem', fontSize: '0.8125rem', fontWeight: 700, color: '#a5b4fc', marginBottom: '0.5rem' }}>
                          <BookOpen size={14} />
                          <span>Peer-Reviewed Scientific References:</span>
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.375rem' }}>
                          {ing.scientific_references.map((ref, sIdx) => (
                            <div key={sIdx} style={{ fontSize: '0.8125rem', color: '#cbd5e1', padding: '0.5rem', background: 'rgba(15, 23, 42, 0.5)', borderRadius: '6px' }}>
                              <strong>"{ref.title}"</strong> ({ref.organization}{ref.publicationYear ? `, ${ref.publicationYear}` : ''}) — {ref.evidenceSummary}
                              {ref.sourceUrl && (
                                <a
                                  href={ref.sourceUrl}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  style={{ color: '#818cf8', marginLeft: '0.5rem', textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: '2px' }}
                                >
                                  PubMed / Source <ExternalLink size={12} />
                                </a>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Unknown Ingredients Breakdown */}
      {hasUnknowns && (
        <div style={{ marginBottom: '1.5rem' }}>
          <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#fbbf24', marginBottom: '0.75rem' }}>
            Unrecognized Ingredients ({result.unknown_ingredients.length}):
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {result.unknown_ingredients.map((unk, idx) => (
              <div
                key={idx}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '0.625rem 0.875rem',
                  background: 'rgba(245, 158, 11, 0.1)',
                  border: '1px solid rgba(245, 158, 11, 0.25)',
                  borderRadius: '8px',
                  fontSize: '0.875rem',
                  color: '#fde68a',
                }}
              >
                <span><strong>{unk.original_name}</strong></span>
                <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>{unk.reason}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
