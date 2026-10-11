import React, { useState, useRef } from 'react';
import { Sparkles, Trash2, ArrowRight, Shield, AlertTriangle, FileText, Upload, Camera, Image as ImageIcon, CheckCircle, RefreshCw } from 'lucide-react';
import { api } from '../services/api';
import type { ImageProcessResponse } from '../types';

interface IngredientInputStepProps {
  onPrepare: (productName: string, rawText: string) => void;
  loading: boolean;
  error: string | null;
}

const PRESET_EXAMPLES = [
  {
    name: 'Gentle Hydrating Cleanser',
    ingredients:
      'Active Ingredients: Water / Aqua (80%), Niacinamide (5%), Glycerin, Panthenol, Sodium Hyaluronate',
  },
  {
    name: 'Exfoliating BHA Serum',
    ingredients:
      'Water, Salicylic- \n Acid (2.0%), • Niacinamide (10% w/w), Glycerin, Zinc PCA, Centella Asiatica Extract',
  },
  {
    name: 'Mineral Sunscreen (Mixed Coverage)',
    ingredients:
      'Ingredients: Zinc Oxide (15%), Water, Cyclopentasiloxane, UnknownChemicalCompoundX, MysteriousExtractY',
  },
];

const MAX_SIZE_MB = 5;
const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp'];

export const IngredientInputStep: React.FC<IngredientInputStepProps> = ({
  onPrepare,
  loading: parentLoading,
  error: parentError,
}) => {
  const [inputMode, setInputMode] = useState<'text' | 'image'>('text');
  const [productName, setProductName] = useState('');
  const [rawText, setRawText] = useState('');
  const [validationError, setValidationError] = useState<string | null>(null);

  // Image Upload State
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [processingImage, setProcessingImage] = useState(false);
  const [, setOcrData] = useState<ImageProcessResponse | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);

  const validateFile = (file: File): string | null => {
    if (!ALLOWED_TYPES.includes(file.type.toLowerCase())) {
      return `Unsupported image format '${file.type || 'unknown'}'. Please select a JPEG, PNG, or WebP image.`;
    }
    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      return `File size (${(file.size / (1024 * 1024)).toFixed(1)} MB) exceeds maximum allowed limit of ${MAX_SIZE_MB} MB.`;
    }
    return null;
  };

  const handleFileSelect = (file: File) => {
    setValidationError(null);
    setOcrData(null);
    const err = validateFile(file);
    if (err) {
      setValidationError(err);
      return;
    }

    setSelectedFile(file);
    const reader = new FileReader();
    reader.onloadend = () => {
      setImagePreview(reader.result as string);
    };
    reader.readAsDataURL(file);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileSelect(e.dataTransfer.files[0]);
    }
  };

  const handleRemoveImage = () => {
    setSelectedFile(null);
    setImagePreview(null);
    setOcrData(null);
    setValidationError(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
    if (cameraInputRef.current) cameraInputRef.current.value = '';
  };

  const handleProcessImage = async () => {
    if (!selectedFile) {
      setValidationError('Please select or capture an ingredient label image first.');
      return;
    }
    setValidationError(null);
    setProcessingImage(true);

    try {
      // Step 1: Secure Upload
      const uploadRes = await api.uploadImage(selectedFile);
      // Step 2: Process OCR Image
      const processRes = await api.processImage(uploadRes.upload_id);
      setOcrData(processRes);

      // Automatically hand off to terms review step with cleaned OCR text
      if (processRes.cleaned_text) {
        onPrepare(productName.trim() || 'Label Scan Product', processRes.cleaned_text);
      } else {
        setValidationError('No readable ingredient text could be extracted from this image. Please try a clearer picture.');
      }
    } catch (err: any) {
      setValidationError(err?.message || 'Failed to process image label.');
    } finally {
      setProcessingImage(false);
    }
  };

  const handleSubmitText = (e: React.FormEvent) => {
    e.preventDefault();
    setValidationError(null);

    if (!rawText || !rawText.trim()) {
      setValidationError('Please paste or enter an ingredient list before preparing.');
      return;
    }

    onPrepare(productName.trim(), rawText.trim());
  };

  const handleClear = () => {
    setProductName('');
    setRawText('');
    handleRemoveImage();
    setValidationError(null);
  };

  const handleApplyPreset = (preset: { name: string; ingredients: string }) => {
    setInputMode('text');
    setProductName(preset.name);
    setRawText(preset.ingredients);
    setValidationError(null);
  };

  const loading = parentLoading || processingImage;

  return (
    <div className="card animate-fade-in" style={{ maxWidth: '840px', margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
        <div style={{ background: 'rgba(14, 165, 233, 0.15)', padding: '0.5rem', borderRadius: '10px', color: '#38bdf8' }}>
          <Shield size={24} />
        </div>
        <div>
          <h1 style={{ fontFamily: 'var(--font-heading)', fontSize: '1.5rem', fontWeight: 700, color: '#f8fafc' }}>
            Cosmetic Ingredient Safety Analysis
          </h1>
          <p style={{ color: '#94a3b8', fontSize: '0.875rem' }}>
            Upload a label photo or paste an ingredient list for canonical INCI matching and safety evaluation.
          </p>
        </div>
      </div>

      {/* Mode Switcher Tabs */}
      <div
        style={{
          display: 'flex',
          background: 'rgba(30, 41, 59, 0.6)',
          borderRadius: '10px',
          padding: '4px',
          margin: '1.25rem 0 1rem',
        }}
      >
        <button
          type="button"
          onClick={() => { setInputMode('text'); setValidationError(null); }}
          style={{
            flex: 1,
            padding: '0.625rem',
            borderRadius: '8px',
            border: 'none',
            background: inputMode === 'text' ? '#0ea5e9' : 'transparent',
            color: inputMode === 'text' ? '#ffffff' : '#94a3b8',
            fontWeight: 600,
            fontSize: '0.875rem',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '0.5rem',
          }}
        >
          <FileText size={16} />
          <span>Manual Text Input</span>
        </button>
        <button
          type="button"
          onClick={() => { setInputMode('image'); setValidationError(null); }}
          style={{
            flex: 1,
            padding: '0.625rem',
            borderRadius: '8px',
            border: 'none',
            background: inputMode === 'image' ? '#0ea5e9' : 'transparent',
            color: inputMode === 'image' ? '#ffffff' : '#94a3b8',
            fontWeight: 600,
            fontSize: '0.875rem',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '0.5rem',
          }}
        >
          <Camera size={16} />
          <span>Photo Upload / OCR Scan</span>
        </button>
      </div>

      {/* Preset Examples Bar */}
      {inputMode === 'text' && (
        <div
          style={{
            marginBottom: '1.25rem',
            padding: '0.75rem 1rem',
            background: 'rgba(30, 41, 59, 0.5)',
            borderRadius: '12px',
            border: '1px solid rgba(255, 255, 255, 0.08)',
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              fontSize: '0.8125rem',
              fontWeight: 600,
              color: '#cbd5e1',
              marginBottom: '0.5rem',
            }}
          >
            <Sparkles size={16} color="#0ea5e9" />
            <span>Quick Example Presets:</span>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
            {PRESET_EXAMPLES.map((preset, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => handleApplyPreset(preset)}
                className="btn btn-secondary"
                style={{ fontSize: '0.8125rem', padding: '0.35rem 0.75rem', borderRadius: '20px' }}
              >
                + {preset.name}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Privacy & Safety Notice */}
      <div
        style={{
          background: 'rgba(15, 23, 42, 0.6)',
          border: '1px solid rgba(14, 165, 233, 0.2)',
          borderRadius: '10px',
          padding: '0.75rem 1rem',
          marginBottom: '1rem',
          fontSize: '0.8125rem',
          color: '#94a3b8',
          display: 'flex',
          flexDirection: 'column',
          gap: '0.375rem',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#38bdf8', fontWeight: 600 }}>
          <Shield size={16} />
          <span>Privacy & Transparency Notice</span>
        </div>
        <div>
          Uploaded image files are processed securely and deleted post-analysis per DToxOut privacy policy.
          Absolute local paths and raw image binary data are never exposed or retained in logs.
        </div>
        <div style={{ fontStyle: 'italic', color: '#cbd5e1' }}>
          * OCR engines may misread ingredient labels. Always review extracted ingredients before safety analysis. Results are informational and not medical advice.
        </div>
      </div>

      {/* Error Banners with Retry */}
      {validationError && (
        <div className="alert-banner alert-warning" style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <AlertTriangle size={18} style={{ flexShrink: 0 }} />
            <div>{validationError}</div>
          </div>
          {selectedFile && (
            <button
              type="button"
              onClick={handleProcessImage}
              className="btn btn-secondary"
              style={{ fontSize: '0.75rem', padding: '0.25rem 0.625rem', flexShrink: 0 }}
            >
              <RefreshCw size={12} /> Retry OCR
            </button>
          )}
        </div>
      )}

      {parentError && (
        <div className="alert-banner alert-danger" style={{ marginBottom: '1rem' }}>
          <AlertTriangle size={18} style={{ flexShrink: 0 }} />
          <div>{parentError}</div>
        </div>
      )}

      {/* Product Name Input */}
      <div style={{ marginBottom: '1.25rem' }}>
        <label
          htmlFor="product-name-input"
          style={{ display: 'block', fontSize: '0.875rem', fontWeight: 600, color: '#e2e8f0', marginBottom: '0.375rem' }}
        >
          Product Name <span style={{ color: '#64748b', fontWeight: 400 }}>(Optional)</span>
        </label>
        <input
          id="product-name-input"
          type="text"
          value={productName}
          onChange={(e) => setProductName(e.target.value)}
          placeholder="e.g. Daily Hydrating Facial Serum"
          style={{
            width: '100%',
            padding: '0.75rem 1rem',
            background: 'rgba(15, 23, 42, 0.8)',
            border: '1px solid rgba(255, 255, 255, 0.12)',
            borderRadius: '10px',
            color: '#ffffff',
            fontSize: '0.9375rem',
          }}
        />
      </div>

      {inputMode === 'text' ? (
        <form onSubmit={handleSubmitText}>
          {/* Multiline Textarea */}
          <div style={{ marginBottom: '1.5rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.375rem' }}>
              <label htmlFor="ingredient-text-input" style={{ fontSize: '0.875rem', fontWeight: 600, color: '#e2e8f0' }}>
                Ingredient List <span style={{ color: '#ef4444' }}>*</span>
              </label>
              <span style={{ fontSize: '0.75rem', color: '#64748b' }}>Separated by commas, semicolons, or lines</span>
            </div>

            <textarea
              id="ingredient-text-input"
              rows={7}
              value={rawText}
              onChange={(e) => setRawText(e.target.value)}
              placeholder="Paste complete ingredient list here...&#10;&#10;e.g. Water / Aqua (80%), Niacinamide (5%), Salicylic Acid (2.0%), Glycerin, Panthenol"
              style={{
                width: '100%',
                padding: '0.875rem 1rem',
                background: 'rgba(15, 23, 42, 0.8)',
                border: '1px solid rgba(255, 255, 255, 0.12)',
                borderRadius: '12px',
                color: '#ffffff',
                fontSize: '0.9375rem',
                lineHeight: 1.5,
                resize: 'vertical',
              }}
            />
          </div>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem' }}>
            <button
              type="button"
              onClick={handleClear}
              disabled={loading || (!productName && !rawText)}
              className="btn btn-secondary"
            >
              <Trash2 size={16} />
              <span>Clear / Reset</span>
            </button>

            <button type="submit" disabled={loading} className="btn btn-primary" style={{ padding: '0.75rem 1.75rem' }}>
              {loading ? (
                <span>Preparing Text...</span>
              ) : (
                <>
                  <FileText size={18} />
                  <span>Prepare & Review Terms</span>
                  <ArrowRight size={16} />
                </>
              )}
            </button>
          </div>
        </form>
      ) : (
        /* Image Upload / Camera Dropzone */
        <div>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            style={{ display: 'none' }}
            onChange={(e) => e.target.files && e.target.files[0] && handleFileSelect(e.target.files[0])}
          />
          <input
            ref={cameraInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            capture="environment"
            style={{ display: 'none' }}
            onChange={(e) => e.target.files && e.target.files[0] && handleFileSelect(e.target.files[0])}
          />

          {!selectedFile ? (
            <div
              onDragOver={handleDragOver}
              onDrop={handleDrop}
              style={{
                border: '2px dashed rgba(14, 165, 233, 0.4)',
                background: 'rgba(15, 23, 42, 0.6)',
                borderRadius: '16px',
                padding: '3rem 1.5rem',
                textAlign: 'center',
                cursor: 'pointer',
                marginBottom: '1.5rem',
                transition: 'all 0.2s ease',
              }}
              onClick={() => fileInputRef.current?.click()}
            >
              <Upload size={42} color="#0ea5e9" style={{ margin: '0 auto 1rem', opacity: 0.9 }} />
              <h3 style={{ fontSize: '1.125rem', fontWeight: 600, color: '#f8fafc', marginBottom: '0.5rem' }}>
                Drag & Drop Ingredient Label Image Here
              </h3>
              <p style={{ color: '#94a3b8', fontSize: '0.875rem', marginBottom: '1.25rem' }}>
                Supports JPEG, PNG, and WebP format up to {MAX_SIZE_MB} MB.
              </p>

              <div style={{ display: 'flex', justifyContent: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); fileInputRef.current?.click(); }}
                  className="btn btn-primary"
                  style={{ fontSize: '0.875rem' }}
                >
                  <ImageIcon size={16} /> Select Photo File
                </button>
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); cameraInputRef.current?.click(); }}
                  className="btn btn-secondary"
                  style={{ fontSize: '0.875rem' }}
                >
                  <Camera size={16} /> Capture Camera Photo
                </button>
              </div>
            </div>
          ) : (
            /* Selected Image Preview Box */
            <div
              className="card"
              style={{
                marginBottom: '1.5rem',
                padding: '1.25rem',
                background: 'rgba(30, 41, 59, 0.6)',
                display: 'flex',
                alignItems: 'center',
                gap: '1.25rem',
                flexWrap: 'wrap',
              }}
            >
              {imagePreview && (
                <img
                  src={imagePreview}
                  alt="Label Preview"
                  style={{ width: '100px', height: '100px', objectFit: 'cover', borderRadius: '10px', border: '1px solid rgba(255, 255, 255, 0.15)' }}
                />
              )}
              <div style={{ flex: 1, minWidth: '200px' }}>
                <div style={{ fontSize: '0.9375rem', fontWeight: 600, color: '#f8fafc', marginBottom: '0.25rem' }}>
                  {selectedFile.name}
                </div>
                <div style={{ color: '#94a3b8', fontSize: '0.8125rem' }}>
                  {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB • {selectedFile.type}
                </div>
                <div style={{ color: '#10b981', fontSize: '0.75rem', marginTop: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
                  <CheckCircle size={14} /> Format & Size Validated
                </div>
              </div>

              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={loading}
                  className="btn btn-secondary"
                  style={{ fontSize: '0.8125rem', padding: '0.4rem 0.75rem' }}
                >
                  Replace Image
                </button>
                <button
                  type="button"
                  onClick={handleRemoveImage}
                  disabled={loading}
                  className="btn"
                  style={{
                    fontSize: '0.8125rem',
                    padding: '0.4rem 0.75rem',
                    background: 'rgba(239, 68, 68, 0.15)',
                    color: '#ef4444',
                    border: '1px solid rgba(239, 68, 68, 0.3)',
                  }}
                >
                  <Trash2 size={14} /> Remove
                </button>
              </div>
            </div>
          )}

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem' }}>
            <button type="button" onClick={handleClear} disabled={loading} className="btn btn-secondary">
              <Trash2 size={16} /> Reset
            </button>

            <button
              type="button"
              onClick={handleProcessImage}
              disabled={loading || !selectedFile}
              className="btn btn-primary"
              style={{ padding: '0.75rem 1.75rem' }}
            >
              {processingImage ? (
                <>
                  <RefreshCw size={18} className="spin" />
                  <span>Extracting OCR Text...</span>
                </>
              ) : (
                <>
                  <Camera size={18} />
                  <span>Extract & Review Terms</span>
                  <ArrowRight size={16} />
                </>
              )}
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
