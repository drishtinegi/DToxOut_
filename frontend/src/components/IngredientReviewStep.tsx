import React, { useState } from 'react';
import {
  CheckCircle,
  AlertTriangle,
  HelpCircle,
  Plus,
  Trash2,
  Edit2,
  ArrowLeft,
  ShieldCheck,
  Info,
} from 'lucide-react';
import type { OCRPrepareResponse, OCRMatchDetail } from '../types';

interface IngredientReviewStepProps {
  productName: string;
  prepareData: OCRPrepareResponse;
  onConfirm: (confirmedTerms: string[]) => void;
  onBack: () => void;
  loading: boolean;
  error: string | null;
}

export const IngredientReviewStep: React.FC<IngredientReviewStepProps> = ({
  productName,
  prepareData,
  onConfirm,
  onBack,
  loading,
  error,
}) => {
  // Local state for candidate terms allowing user edits
  const [terms, setTerms] = useState<string[]>(prepareData.candidate_terms || []);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [editingText, setEditingText] = useState<string>('');
  const [newTermInput, setNewTermInput] = useState<string>('');

  const matchMap = new Map<string, OCRMatchDetail>();
  (prepareData.match_details || []).forEach((detail) => {
    matchMap.set(detail.candidate_term.toLowerCase(), detail);
  });

  const handleStartEdit = (index: number, currentText: string) => {
    setEditingIndex(index);
    setEditingText(currentText);
  };

  const handleSaveEdit = (index: number) => {
    if (!editingText.trim()) return;
    const updated = [...terms];
    updated[index] = editingText.trim();
    setTerms(updated);
    setEditingIndex(null);
    setEditingText('');
  };

  const handleDeleteTerm = (index: number) => {
    const updated = terms.filter((_, i) => i !== index);
    setTerms(updated);
    if (editingIndex === index) {
      setEditingIndex(null);
    }
  };

  const handleAddTerm = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTermInput.trim()) return;
    setTerms([...terms, newTermInput.trim()]);
    setNewTermInput('');
  };

  const handleConfirm = () => {
    onConfirm(terms);
  };

  // Group terms by match type
  const recognizedTerms: string[] = [];
  const fuzzyTerms: string[] = [];
  const unknownTerms: string[] = [];

  terms.forEach((t) => {
    const detail = matchMap.get(t.toLowerCase());
    if (!detail || detail.match_type === 'UNKNOWN') {
      unknownTerms.push(t);
    } else if (detail.match_type === 'FUZZY') {
      fuzzyTerms.push(t);
    } else {
      recognizedTerms.push(t);
    }
  });

  const confidenceScore = prepareData.parser_confidence ?? 0.0;

  return (
    <div className="card animate-fade-in" style={{ maxWidth: '920px', margin: '0 auto' }}>
      {/* Header */}
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
              fontSize: '1.375rem',
              fontWeight: 700,
              color: '#f8fafc',
            }}
          >
            Step 2: Ingredient Preparation & Verification
          </h2>
          {productName && (
            <p style={{ color: '#0ea5e9', fontSize: '0.875rem', fontWeight: 600 }}>
              Product: {productName}
            </p>
          )}
        </div>

        <button onClick={onBack} className="btn btn-secondary" style={{ padding: '0.5rem 0.875rem' }}>
          <ArrowLeft size={16} />
          <span>Edit Raw Text</span>
        </button>
      </div>

      {/* OCR Engine & Parser Confidence Gauge Bar */}
      <div
        style={{
          background: 'rgba(15, 23, 42, 0.8)',
          borderRadius: '12px',
          padding: '1.25rem',
          marginBottom: '1.5rem',
          border: '1px solid rgba(255, 255, 255, 0.08)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem', flexWrap: 'wrap', gap: '0.5rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 600, fontSize: '0.875rem' }}>
            <Info size={18} color="#0ea5e9" />
            <span>OCR Extraction & Parser Confidence</span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            {(prepareData as any).ocr_provider && (
              <span
                style={{
                  fontSize: '0.75rem',
                  padding: '0.2rem 0.6rem',
                  borderRadius: '12px',
                  background: 'rgba(14, 165, 233, 0.15)',
                  color: '#38bdf8',
                  border: '1px solid rgba(14, 165, 233, 0.3)',
                  fontWeight: 600,
                }}
              >
                Provider: {(prepareData as any).ocr_provider}
              </span>
            )}
            {(prepareData as any).processing_duration_ms > 0 && (
              <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
                {(prepareData as any).processing_duration_ms} ms
              </span>
            )}
            <div
              style={{
                fontSize: '1rem',
                fontWeight: 800,
                color: confidenceScore >= 75 ? '#34d399' : '#fbbf24',
              }}
            >
              {confidenceScore}%
            </div>
          </div>
        </div>

        <div style={{ width: '100%', height: '8px', background: 'rgba(255, 255, 255, 0.1)', borderRadius: '4px', overflow: 'hidden' }}>
          <div
            style={{
              width: `${confidenceScore}%`,
              height: '100%',
              background: confidenceScore >= 75 ? '#10b981' : '#f59e0b',
              transition: 'width 0.4s ease',
            }}
          />
        </div>

        <p style={{ fontSize: '0.75rem', color: '#94a3b8', marginTop: '0.5rem' }}>
          Text preprocessed by DToxOut cleaner (headers stripped, line-breaks merged, percentages removed).
          OCR may misread ingredient labels. Review extracted ingredients before analysis. Results are informational and not medical advice.
        </p>
      </div>

      {/* Warnings & Alerts */}
      {prepareData.review_required && (
        <div className="alert-banner alert-warning">
          <AlertTriangle size={20} style={{ flexShrink: 0 }} />
          <div>
            <strong>Verification Recommended:</strong> Parser confidence is {confidenceScore}% or unrecognized terms exist. Please inspect candidate terms below before running safety analysis.
          </div>
        </div>
      )}

      {prepareData.warnings && prepareData.warnings.length > 0 && (
        <div style={{ marginBottom: '1.25rem' }}>
          {prepareData.warnings.map((warn, i) => (
            <div key={i} className="alert-banner alert-info" style={{ padding: '0.625rem 1rem', fontSize: '0.8125rem' }}>
              <Info size={16} />
              <span>{warn}</span>
            </div>
          ))}
        </div>
      )}

      {error && (
        <div className="alert-banner alert-danger">
          <AlertTriangle size={18} style={{ flexShrink: 0 }} />
          <div>{error}</div>
        </div>
      )}

      {/* Terms Summary Metrics */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          gap: '0.875rem',
          marginBottom: '1.5rem',
        }}
      >
        <div style={{ background: 'rgba(16, 185, 129, 0.1)', border: '1px solid rgba(16, 185, 129, 0.25)', padding: '0.875rem', borderRadius: '10px', textAlign: 'center' }}>
          <div style={{ fontSize: '1.25rem', fontWeight: 800, color: '#34d399' }}>{recognizedTerms.length}</div>
          <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Exact INCI / Alias</div>
        </div>

        <div style={{ background: 'rgba(99, 102, 241, 0.1)', border: '1px solid rgba(99, 102, 241, 0.25)', padding: '0.875rem', borderRadius: '10px', textAlign: 'center' }}>
          <div style={{ fontSize: '1.25rem', fontWeight: 800, color: '#a5b4fc' }}>{fuzzyTerms.length}</div>
          <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Fuzzy Matches</div>
        </div>

        <div style={{ background: 'rgba(245, 158, 11, 0.1)', border: '1px solid rgba(245, 158, 11, 0.25)', padding: '0.875rem', borderRadius: '10px', textAlign: 'center' }}>
          <div style={{ fontSize: '1.25rem', fontWeight: 800, color: '#fbbf24' }}>{unknownTerms.length}</div>
          <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Unrecognized</div>
        </div>
      </div>

      {/* Candidate Terms List with Inline Edit & Delete */}
      <div style={{ marginBottom: '1.5rem' }}>
        <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#e2e8f0', marginBottom: '0.875rem' }}>
          Extracted Candidate Terms ({terms.length}):
        </h3>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', maxHeight: '360px', overflowY: 'auto', paddingRight: '0.25rem' }}>
          {terms.map((term, index) => {
            const detail = matchMap.get(term.toLowerCase());
            const isEditing = editingIndex === index;

            return (
              <div
                key={index}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '0.75rem',
                  padding: '0.625rem 0.875rem',
                  background: 'rgba(15, 23, 42, 0.6)',
                  border: '1px solid rgba(255, 255, 255, 0.08)',
                  borderRadius: '8px',
                }}
              >
                {isEditing ? (
                  <div style={{ flex: 1, display: 'flex', gap: '0.5rem' }}>
                    <input
                      type="text"
                      value={editingText}
                      onChange={(e) => setEditingText(e.target.value)}
                      style={{
                        flex: 1,
                        padding: '0.375rem 0.625rem',
                        background: '#0f172a',
                        border: '1px solid #0ea5e9',
                        borderRadius: '6px',
                        color: '#ffffff',
                        fontSize: '0.875rem',
                      }}
                    />
                    <button onClick={() => handleSaveEdit(index)} className="btn btn-primary" style={{ padding: '0.375rem 0.75rem', fontSize: '0.75rem' }}>
                      Save
                    </button>
                  </div>
                ) : (
                  <>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem', flex: 1 }}>
                      {detail?.match_type === 'EXACT_INCI' || detail?.match_type === 'EXACT_ALIAS' || detail?.match_type === 'EXACT_COMMON_NAME' ? (
                        <CheckCircle size={16} color="#34d399" />
                      ) : detail?.match_type === 'FUZZY' ? (
                        <HelpCircle size={16} color="#a5b4fc" />
                      ) : (
                        <AlertTriangle size={16} color="#fbbf24" />
                      )}
                      <span style={{ fontSize: '0.9375rem', fontWeight: 500, color: '#f8fafc' }}>
                        {term}
                      </span>

                      {detail?.matched_inci && detail.matched_inci.toLowerCase() !== term.toLowerCase() && (
                        <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
                          (INCI: {detail.matched_inci})
                        </span>
                      )}
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <span
                        className={`badge ${
                          detail?.match_type === 'FUZZY'
                            ? 'badge-fuzzy'
                            : detail?.match_type === 'UNKNOWN' || !detail
                            ? 'badge-unknown'
                            : 'badge-low'
                        }`}
                        style={{ fontSize: '0.7rem' }}
                      >
                        {detail?.match_type || 'UNKNOWN'}
                      </span>

                      <button
                        onClick={() => handleStartEdit(index, term)}
                        style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', padding: '0.25rem' }}
                        title="Edit term"
                      >
                        <Edit2 size={14} />
                      </button>

                      <button
                        onClick={() => handleDeleteTerm(index)}
                        style={{ background: 'none', border: 'none', color: '#f87171', cursor: 'pointer', padding: '0.25rem' }}
                        title="Delete term"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Add New Term Input */}
      <form onSubmit={handleAddTerm} style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem' }}>
        <input
          type="text"
          value={newTermInput}
          onChange={(e) => setNewTermInput(e.target.value)}
          placeholder="Add another ingredient term..."
          style={{
            flex: 1,
            padding: '0.625rem 0.875rem',
            background: 'rgba(15, 23, 42, 0.8)',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            borderRadius: '8px',
            color: '#ffffff',
            fontSize: '0.875rem',
          }}
        />
        <button type="submit" className="btn btn-secondary">
          <Plus size={16} />
          <span>Add Term</span>
        </button>
      </form>

      {/* Action Footer */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: '1rem', borderTop: '1px solid rgba(255, 255, 255, 0.1)' }}>
        <button onClick={onBack} className="btn btn-secondary">
          <ArrowLeft size={16} />
          <span>Back</span>
        </button>

        <button
          onClick={handleConfirm}
          disabled={loading || terms.length === 0}
          className="btn btn-primary"
          style={{ padding: '0.75rem 1.75rem' }}
        >
          {loading ? (
            <span>Analyzing Ingredients...</span>
          ) : (
            <>
              <ShieldCheck size={18} />
              <span>Confirm & Run Safety Analysis</span>
            </>
          )}
        </button>
      </div>
    </div>
  );
};
