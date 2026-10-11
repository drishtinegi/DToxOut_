import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import App from '../App';
import { api, authStorage } from '../services/api';
import type { ImageUploadResponse, ImageProcessResponse, ScanHistoryItem, ScanHistoryDetail } from '../types';

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
      uploadImage: vi.fn(),
      processImage: vi.fn(),
      getScanHistory: vi.fn(),
      getScanDetails: vi.fn(),
      deleteScan: vi.fn(),
    },
  };
});

const mockUploadResponse: ImageUploadResponse = {
  upload_id: 'upload-uuid-123',
  safe_filename: 'upload-uuid-123.jpg',
  media_type: 'image/jpeg',
  file_size: 1024,
  status: 'success',
};

const mockProcessResponse: ImageProcessResponse = {
  upload_id: 'upload-uuid-123',
  raw_text: 'INGREDIENTS: Water, Niacinamide, Glycerin.',
  cleaned_text: 'Water, Niacinamide, Glycerin',
  candidate_terms: ['Water', 'Niacinamide', 'Glycerin'],
  match_details: [
    { candidate_term: 'Water', match_type: 'EXACT_INCI', matched_inci: 'Water', confidence_score: 1.0, manual_confirmation_recommended: false, reason: 'Exact match' },
    { candidate_term: 'Niacinamide', match_type: 'EXACT_INCI', matched_inci: 'Niacinamide', confidence_score: 1.0, manual_confirmation_recommended: false, reason: 'Exact match' },
    { candidate_term: 'Glycerin', match_type: 'EXACT_INCI', matched_inci: 'Glycerin', confidence_score: 1.0, manual_confirmation_recommended: false, reason: 'Exact match' },
  ],
  ocr_provider: 'DevMockOCRProvider',
  ocr_confidence: 0.95,
  parser_confidence: 100.0,
  processing_duration_ms: 15.0,
  review_required: false,
  warnings: [],
  recognized_count: 3,
  unknown_count: 0,
};

const mockHistoryItems: ScanHistoryItem[] = [
  {
    id: 'scan-history-1',
    product_name: 'Daily Hydrating Serum',
    overall_score: 8.5,
    overall_risk: 'LOW',
    ingredient_count: 5,
    created_at: '2026-09-13T10:00:00Z',
  },
];

const mockHistoryDetail: ScanHistoryDetail = {
  id: 'scan-history-1',
  product_name: 'Daily Hydrating Serum',
  overall_score: 8.5,
  overall_risk: 'LOW',
  ingredient_count: 5,
  created_at: '2026-09-13T10:00:00Z',
  ingredients: ['Water', 'Glycerin', 'Niacinamide', 'Panthenol', 'Sodium Hyaluronate'],
};

describe('Phase 4 Frontend — Image Upload & Scan History', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();

    const mockUser = { id: 'u1', email: 'demo@dtoxout.org', username: 'demouser', role: 'USER' as const };
    vi.mocked(api.getCurrentUser).mockResolvedValue(mockUser);

    vi.mocked(api.quickDemoLogin).mockImplementation(async () => {
      authStorage.setToken('fake-jwt-token');
      authStorage.setUser(mockUser);
      return { access_token: 'fake-jwt-token', token_type: 'bearer', user: mockUser };
    });
  });

  it('switches input mode to photo upload and validates file size / format', async () => {
    render(<App />);

    const photoTab = screen.getByRole('button', { name: /Photo Upload \/ OCR Scan/i });
    fireEvent.click(photoTab);

    expect(screen.getByText(/Drag & Drop Ingredient Label Image Here/i)).toBeInTheDocument();
  });

  it('handles image upload and process image flow into terms review', async () => {
    vi.mocked(api.uploadImage).mockResolvedValue(mockUploadResponse);
    vi.mocked(api.processImage).mockResolvedValue(mockProcessResponse);

    render(<App />);

    fireEvent.click(screen.getByRole('button', { name: /Photo Upload \/ OCR Scan/i }));

    const file = new File(['dummy_image_data'], 'label.jpg', { type: 'image/jpeg' });
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;

    Object.defineProperty(fileInput, 'files', { value: [file] });
    fireEvent.change(fileInput);

    expect(await screen.findByText('label.jpg')).toBeInTheDocument();
    expect(screen.getByText(/Format & Size Validated/i)).toBeInTheDocument();

    const processBtn = screen.getByRole('button', { name: /Extract & Review Terms/i });
    fireEvent.click(processBtn);

    await waitFor(() => {
      expect(api.uploadImage).toHaveBeenCalledWith(file);
      expect(api.processImage).toHaveBeenCalledWith('upload-uuid-123');
    });
  });

  it('renders Scan History view and handles details viewing and deletion', async () => {
    vi.mocked(api.getScanHistory).mockResolvedValue(mockHistoryItems);
    vi.mocked(api.getScanDetails).mockResolvedValue(mockHistoryDetail);
    vi.mocked(api.deleteScan).mockResolvedValue({ message: 'Scan deleted successfully' });
    window.confirm = vi.fn().mockReturnValue(true);

    // Simulate logged in user
    authStorage.setToken('fake-token');
    authStorage.setUser({ id: 'u1', email: 'demo@dtoxout.org', username: 'demouser', role: 'USER' });

    render(<App />);

    const historyNavBtn = screen.getByRole('button', { name: /Scan History/i });
    fireEvent.click(historyNavBtn);

    expect(await screen.findByText('Daily Hydrating Serum')).toBeInTheDocument();
    expect(screen.getByText('8.5')).toBeInTheDocument();
    expect(screen.getByText('LOW RISK')).toBeInTheDocument();

    // Open Details Modal
    const detailsBtn = screen.getByRole('button', { name: /Details/i });
    fireEvent.click(detailsBtn);

    expect(await screen.findByText('Analyzed Ingredients (5)')).toBeInTheDocument();
    expect(screen.getByText('Sodium Hyaluronate')).toBeInTheDocument();

    // Close Modal
    fireEvent.click(screen.getByRole('button', { name: /Close/i }));

    // Delete Scan
    const deleteBtn = screen.getByTitle('Delete Scan');
    fireEvent.click(deleteBtn);

    await waitFor(() => {
      expect(api.deleteScan).toHaveBeenCalledWith('scan-history-1');
    });
  });
});
