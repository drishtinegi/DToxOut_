import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { IngredientInputStep } from '../components/IngredientInputStep';
import { IngredientReviewStep } from '../components/IngredientReviewStep';
import type { ImageProcessResponse } from '../types';

describe('Phase 5 Frontend OCR & Privacy Integration', () => {
  it('renders privacy notice and disclaimers in IngredientInputStep', () => {
    const onPrepareMock = vi.fn();
    render(
      <IngredientInputStep
        onPrepare={onPrepareMock}
        loading={false}
        error={null}
      />
    );

    expect(screen.getByText(/Privacy & Transparency Notice/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Uploaded image files are processed securely and deleted post-analysis/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/OCR engines may misread ingredient labels/i)
    ).toBeInTheDocument();
  });

  it('renders OCR provider name, confidence gauge, and duration in IngredientReviewStep', () => {
    const mockPrepareData: ImageProcessResponse = {
      upload_id: 'test-uuid-1234',
      raw_text: 'INGREDIENTS: Water, Niacinamide, Glycerin',
      cleaned_text: 'Water, Niacinamide, Glycerin',
      candidate_terms: ['Water', 'Niacinamide', 'Glycerin'],
      match_details: [
        {
          candidate_term: 'Water',
          match_type: 'EXACT_INCI',
          matched_inci: 'Water',
          confidence_score: 1.0,
          manual_confirmation_recommended: false,
          reason: 'Exact INCI match',
        },
      ],
      ocr_provider: 'TesseractOCRProvider',
      ocr_confidence: 0.92,
      parser_confidence: 95.0,
      processing_duration_ms: 245.5,
      review_required: false,
      warnings: [],
      recognized_count: 3,
      unknown_count: 0,
    };

    const onConfirmMock = vi.fn();
    const onBackMock = vi.fn();

    render(
      <IngredientReviewStep
        productName="Hydrating Serum"
        prepareData={mockPrepareData as any}
        onConfirm={onConfirmMock}
        onBack={onBackMock}
        loading={false}
        error={null}
      />
    );

    expect(screen.getByText(/Provider: TesseractOCRProvider/i)).toBeInTheDocument();
    expect(screen.getByText(/245.5 ms/i)).toBeInTheDocument();
    expect(screen.getByText(/95%/i)).toBeInTheDocument();
    expect(screen.getByText(/Confirm & Run Safety Analysis/i)).toBeInTheDocument();
  });

  it('triggers onConfirm callback with edited terms when user confirms', () => {
    const mockPrepareData: ImageProcessResponse = {
      upload_id: 'test-uuid-5678',
      raw_text: 'INGREDIENTS: Aqua, Glycerin',
      cleaned_text: 'Aqua, Glycerin',
      candidate_terms: ['Aqua', 'Glycerin'],
      match_details: [],
      ocr_provider: 'DevMockOCRProvider',
      ocr_confidence: 0.95,
      parser_confidence: 90.0,
      processing_duration_ms: 15.0,
      review_required: false,
      warnings: [],
      recognized_count: 2,
      unknown_count: 0,
    };

    const onConfirmMock = vi.fn();
    const onBackMock = vi.fn();

    render(
      <IngredientReviewStep
        productName="Test Cream"
        prepareData={mockPrepareData as any}
        onConfirm={onConfirmMock}
        onBack={onBackMock}
        loading={false}
        error={null}
      />
    );

    const confirmBtn = screen.getByText(/Confirm & Run Safety Analysis/i);
    fireEvent.click(confirmBtn);

    expect(onConfirmMock).toHaveBeenCalledTimes(1);
    expect(onConfirmMock).toHaveBeenCalledWith(['Aqua', 'Glycerin']);
  });
});
