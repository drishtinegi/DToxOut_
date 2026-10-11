import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import App from '../App';
import { api, authStorage } from '../services/api';
import type { OCRPrepareResponse, ScanResponse } from '../types';

// Mock API service methods
vi.mock('../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/api')>();
  return {
    ...actual,
    api: {
      ...actual.api,
      login: vi.fn(),
      register: vi.fn(),
      getCurrentUser: vi.fn(),
      quickDemoLogin: vi.fn(),
      prepareText: vi.fn(),
      analyzeIngredients: vi.fn(),
    },
  };
});

const mockPrepareResponse: OCRPrepareResponse = {
  raw_text: 'Active Ingredients: Salicylic Acid (2%), Water, UnknownCompX',
  cleaned_text: 'Salicylic Acid, Water, UnknownCompX',
  candidate_terms: ['Salicylic Acid', 'Water', 'UnknownCompX'],
  match_details: [
    {
      candidate_term: 'Salicylic Acid',
      match_type: 'EXACT_INCI',
      matched_inci: 'Salicylic Acid',
      confidence_score: 1.0,
      manual_confirmation_recommended: false,
      reason: 'Exact INCI match found',
    },
    {
      candidate_term: 'Water',
      match_type: 'EXACT_INCI',
      matched_inci: 'Water',
      confidence_score: 1.0,
      manual_confirmation_recommended: false,
      reason: 'Exact INCI match found',
    },
    {
      candidate_term: 'UnknownCompX',
      match_type: 'UNKNOWN',
      matched_inci: null,
      confidence_score: 0.0,
      manual_confirmation_recommended: false,
      reason: 'Not found in knowledge base',
    },
  ],
  parser_confidence: 66.7,
  review_required: true,
  warnings: ['Stripped ingredient header(s): Active Ingredients:'],
  candidate_count: 3,
  recognized_count: 2,
  unknown_count: 1,
};

const mockScanResponse: ScanResponse = {
  id: 'scan-123',
  overall_score: 7.2,
  overall_risk: 'MODERATE',
  confidence_score: 66,
  recognition_coverage: 66.7,
  recommendation: {
    status: 'USE WITH CAUTION',
    summary: 'Contains unknown ingredients; coverage is incomplete.',
    warnings: [
      {
        type: 'INCOMPLETE_COVERAGE',
        title: 'Unknown Ingredients',
        message: 'Safety profile incomplete due to unrecognized terms.',
      },
    ],
  },
  disclaimer: 'DToxOut analysis results are informational only and do not constitute a medical diagnosis.',
  recognized_ingredients: [
    {
      inci_name: 'Salicylic Acid',
      common_name: 'BHA',
      description: 'Beta hydroxy acid exfoliant',
      function: 'Exfoliant',
      safety_rating: 6.5,
      evidence_level: 'HIGH',
      risk: 'MODERATE',
      match_type: 'EXACT_INCI',
      match_confidence: 1.0,
      regulations: [
        {
          country: 'European Union',
          jurisdiction: 'EU',
          regulatoryStatus: 'RESTRICTED',
          restrictionDetails: 'Max concentration 2.0% in leave-on products',
          source: 'EU Cosmetic Regulation',
          sourceUrl: 'https://ec.europa.eu/growth/tools-databases/cosing/',
        },
      ],
      scientific_references: [
        {
          title: 'Safety Assessment of Salicylic Acid',
          organization: 'CIR Panel',
          publicationYear: 2019,
          evidenceSummary: 'Safe when formulated to avoid irritation',
          sourceUrl: 'https://pubmed.ncbi.nlm.nih.gov/12345678/',
        },
      ],
    },
    {
      inci_name: 'Water',
      common_name: 'Aqua',
      description: 'Solvent',
      function: 'Solvent',
      safety_rating: 10.0,
      evidence_level: 'VERY_HIGH',
      risk: 'LOW',
      match_type: 'EXACT_INCI',
      match_confidence: 1.0,
    },
  ],
  unknown_ingredients: [
    {
      original_name: 'UnknownCompX',
      status: 'UNKNOWN',
      reason: 'Not found in DToxOut knowledge base.',
    },
  ],
};

describe('DToxOut Frontend App', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();

    // Default mock setup for quickDemoLogin to persist token in tests
    vi.mocked(api.quickDemoLogin).mockImplementation(async () => {
      authStorage.setToken('fake-jwt-token');
      const mockUser = { id: 'u1', email: 'demo@dtoxout.org', username: 'demouser', role: 'USER' as const };
      authStorage.setUser(mockUser);
      return { access_token: 'fake-jwt-token', token_type: 'bearer', user: mockUser };
    });
  });

  it('renders landing screen with input validation', async () => {
    render(<App />);

    expect(screen.getByRole('heading', { name: /Cosmetic Ingredient/i })).toBeInTheDocument();
    const prepareButton = screen.getByRole('button', { name: /Prepare & Review Terms/i });

    // Clicking without text shows validation error
    fireEvent.click(prepareButton);
    expect(await screen.findByText(/Please paste or enter an ingredient list/i)).toBeInTheDocument();
  });

  it('handles quick demo authentication, text preparation, and term review', async () => {
    vi.mocked(api.prepareText).mockResolvedValue(mockPrepareResponse);

    render(<App />);

    const textarea = screen.getByPlaceholderText(/Paste complete ingredient list here/i);
    fireEvent.change(textarea, { target: { value: 'Active Ingredients: Salicylic Acid (2%), Water, UnknownCompX' } });

    const prepareButton = screen.getByRole('button', { name: /Prepare & Review Terms/i });
    fireEvent.click(prepareButton);

    await waitFor(() => {
      expect(screen.getByText(/Step 2: Ingredient Preparation & Verification/i)).toBeInTheDocument();
    });

    expect(screen.getByText('Salicylic Acid')).toBeInTheDocument();
    expect(screen.getByText('Water')).toBeInTheDocument();
    expect(screen.getByText('UnknownCompX')).toBeInTheDocument();
    expect(screen.getByText('66.7%')).toBeInTheDocument();
    expect(screen.getByText(/Stripped ingredient header/i)).toBeInTheDocument();
  });

  it('allows term editing, deletion, and adding before final confirmation', async () => {
    vi.mocked(api.prepareText).mockResolvedValue(mockPrepareResponse);
    vi.mocked(api.analyzeIngredients).mockResolvedValue(mockScanResponse);

    render(<App />);

    const textarea = screen.getByPlaceholderText(/Paste complete ingredient list here/i);
    fireEvent.change(textarea, { target: { value: 'Water, Niacinamide' } });
    fireEvent.click(screen.getByRole('button', { name: /Prepare & Review Terms/i }));

    await screen.findByText(/Step 2: Ingredient Preparation & Verification/i);

    // Delete 'UnknownCompX' term
    const deleteButtons = screen.getAllByTitle('Delete term');
    fireEvent.click(deleteButtons[2]);

    expect(screen.queryByText('UnknownCompX')).not.toBeInTheDocument();

    // Confirm final analysis
    const confirmButton = screen.getByRole('button', { name: /Confirm & Run Safety Analysis/i });
    fireEvent.click(confirmButton);

    await waitFor(() => {
      expect(screen.getByText(/Ingredient Safety Analysis Results/i)).toBeInTheDocument();
    });

    // Check Results Screen elements
    expect(screen.getByText(/7.2 /i)).toBeInTheDocument();
    expect(screen.getAllByText('MODERATE')[0]).toBeInTheDocument();
    expect(screen.getByText(/Incomplete Ingredient Coverage/i)).toBeInTheDocument();
    expect(screen.getByText(/Max concentration 2.0% in leave-on products/i)).toBeInTheDocument();

    // Check regulatory source link security attributes
    const sourceLinks = screen.getAllByRole('link', { name: /Source Link/i });
    expect(sourceLinks[0]).toHaveAttribute('target', '_blank');
    expect(sourceLinks[0]).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('handles API network failure state gracefully', async () => {
    vi.mocked(api.prepareText).mockRejectedValue(
      new Error('Unable to connect to DToxOut backend API.')
    );

    render(<App />);

    const textarea = screen.getByPlaceholderText(/Paste complete ingredient list here/i);
    fireEvent.change(textarea, { target: { value: 'Water, Niacinamide' } });
    fireEvent.click(screen.getByRole('button', { name: /Prepare & Review Terms/i }));

    expect(await screen.findByText(/Unable to connect to DToxOut backend API/i)).toBeInTheDocument();
  });
});
