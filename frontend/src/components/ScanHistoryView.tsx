import React, { useState, useEffect } from 'react';
import { History, Trash2, Eye, Shield, Calendar, AlertCircle, RefreshCw, X } from 'lucide-react';
import { api } from '../services/api';
import type { ScanHistoryItem, ScanHistoryDetail } from '../types';

interface ScanHistoryViewProps {
  onNewAnalysis: () => void;
}

export const ScanHistoryView: React.FC<ScanHistoryViewProps> = ({ onNewAnalysis }) => {
  const [scans, setScans] = useState<ScanHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedScan, setSelectedScan] = useState<ScanHistoryDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const fetchHistory = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getScanHistory();
      setScans(data);
    } catch (err: any) {
      setError(err?.message || 'Failed to load scan history.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHistory();
  }, []);

  const handleOpenDetail = async (scanId: string) => {
    setLoadingDetail(true);
    try {
      const detail = await api.getScanDetails(scanId);
      setSelectedScan(detail);
    } catch (err: any) {
      alert(err?.message || 'Failed to load scan details.');
    } finally {
      setLoadingDetail(false);
    }
  };

  const handleDeleteScan = async (scanId: string) => {
    if (!window.confirm('Are you sure you want to delete this scan history record?')) {
      return;
    }
    setDeletingId(scanId);
    try {
      await api.deleteScan(scanId);
      setScans((prev) => prev.filter((s) => s.id !== scanId));
      if (selectedScan?.id === scanId) {
        setSelectedScan(null);
      }
    } catch (err: any) {
      alert(err?.message || 'Failed to delete scan.');
    } finally {
      setDeletingId(null);
    }
  };

  const getRiskBadgeColor = (risk: string) => {
    switch (risk?.toUpperCase()) {
      case 'LOW':
        return { bg: 'rgba(16, 185, 129, 0.15)', text: '#10b981', border: 'rgba(16, 185, 129, 0.3)' };
      case 'MODERATE':
        return { bg: 'rgba(245, 158, 11, 0.15)', text: '#f59e0b', border: 'rgba(245, 158, 11, 0.3)' };
      case 'HIGH':
      case 'VERY_HIGH':
        return { bg: 'rgba(239, 68, 68, 0.15)', text: '#ef4444', border: 'rgba(239, 68, 68, 0.3)' };
      default:
        return { bg: 'rgba(148, 163, 184, 0.15)', text: '#94a3b8', border: 'rgba(148, 163, 184, 0.3)' };
    }
  };

  return (
    <div className="animate-fade-in" style={{ maxWidth: '900px', margin: '0 auto', padding: '0 1rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <div>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 700, color: '#f8fafc', display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
            <History size={26} color="#0ea5e9" />
            <span>Your Scan History</span>
          </h1>
          <p style={{ color: '#94a3b8', fontSize: '0.875rem', marginTop: '0.25rem' }}>
            View and manage your previously analyzed cosmetic products.
          </p>
        </div>
        <button onClick={onNewAnalysis} className="btn btn-primary" style={{ fontSize: '0.875rem' }}>
          + New Ingredient Analysis
        </button>
      </div>

      {error && (
        <div className="alert-banner alert-danger" style={{ marginBottom: '1.5rem' }}>
          <AlertCircle size={20} />
          <div style={{ flex: 1 }}>{error}</div>
          <button onClick={fetchHistory} className="btn btn-secondary" style={{ padding: '0.3rem 0.6rem', fontSize: '0.75rem' }}>
            <RefreshCw size={12} /> Retry
          </button>
        </div>
      )}

      {loading ? (
        <div className="card" style={{ padding: '3rem', textAlign: 'center', color: '#94a3b8' }}>
          <RefreshCw size={32} className="spin" style={{ margin: '0 auto 1rem', display: 'block', color: '#0ea5e9' }} />
          <p>Loading your scan history...</p>
        </div>
      ) : scans.length === 0 ? (
        <div className="card" style={{ padding: '3rem', textAlign: 'center' }}>
          <Shield size={48} color="#64748b" style={{ margin: '0 auto 1rem', opacity: 0.6 }} />
          <h3 style={{ fontSize: '1.125rem', color: '#f8fafc', fontWeight: 600, marginBottom: '0.5rem' }}>No Scans Saved Yet</h3>
          <p style={{ color: '#94a3b8', fontSize: '0.875rem', maxWidth: '400px', margin: '0 auto 1.5rem' }}>
            When you perform cosmetic safety analyses, your scan results will be saved securely here.
          </p>
          <button onClick={onNewAnalysis} className="btn btn-primary">
            Analyze First Product
          </button>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {scans.map((scan) => {
            const riskColors = getRiskBadgeColor(scan.overall_risk);
            const dateStr = new Date(scan.created_at || scan.createdAt || '').toLocaleDateString(undefined, {
              year: 'numeric',
              month: 'short',
              day: 'numeric',
              hour: '2-digit',
              minute: '2-digit',
            });

            return (
              <div
                key={scan.id}
                className="card"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '1.25rem',
                  gap: '1rem',
                  flexWrap: 'wrap',
                }}
              >
                <div style={{ flex: 1, minWidth: '220px' }}>
                  <h3 style={{ fontSize: '1.0625rem', fontWeight: 600, color: '#f8fafc', marginBottom: '0.375rem' }}>
                    {scan.product_name || 'Cosmetic Product Scan'}
                  </h3>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', color: '#94a3b8', fontSize: '0.8125rem' }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
                      <Calendar size={14} />
                      {dateStr}
                    </span>
                    <span>•</span>
                    <span>{scan.ingredient_count} Ingredients</span>
                  </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#f8fafc' }}>
                      {scan.overall_score.toFixed(1)} <span style={{ fontSize: '0.75rem', color: '#64748b' }}>/ 10</span>
                    </div>
                    <span
                      style={{
                        display: 'inline-block',
                        padding: '0.15rem 0.5rem',
                        borderRadius: '4px',
                        fontSize: '0.6875rem',
                        fontWeight: 600,
                        backgroundColor: riskColors.bg,
                        color: riskColors.text,
                        border: `1px solid ${riskColors.border}`,
                        marginTop: '0.2rem',
                      }}
                    >
                      {scan.overall_risk} RISK
                    </span>
                  </div>

                  <div style={{ display: 'flex', gap: '0.5rem' }}>
                    <button
                      onClick={() => handleOpenDetail(scan.id)}
                      disabled={loadingDetail}
                      className="btn btn-secondary"
                      style={{ padding: '0.45rem 0.75rem', fontSize: '0.8125rem' }}
                      title="View Scan Details"
                    >
                      <Eye size={14} />
                      <span>Details</span>
                    </button>
                    <button
                      onClick={() => handleDeleteScan(scan.id)}
                      disabled={deletingId === scan.id}
                      className="btn"
                      style={{
                        padding: '0.45rem 0.75rem',
                        fontSize: '0.8125rem',
                        background: 'rgba(239, 68, 68, 0.1)',
                        color: '#ef4444',
                        border: '1px solid rgba(239, 68, 68, 0.25)',
                      }}
                      title="Delete Scan"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Modal for Details */}
      {selectedScan && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.8)',
            backdropFilter: 'blur(8px)',
            zIndex: 300,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '1rem',
          }}
          onClick={() => setSelectedScan(null)}
        >
          <div
            className="card animate-fade-in"
            style={{
              width: '100%',
              maxWidth: '650px',
              maxHeight: '85vh',
              overflowY: 'auto',
              background: '#0f172a',
              border: '1px solid rgba(255, 255, 255, 0.15)',
              position: 'relative',
              padding: '1.75rem',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={() => setSelectedScan(null)}
              style={{
                position: 'absolute',
                top: '1rem',
                right: '1rem',
                background: 'none',
                border: 'none',
                color: '#94a3b8',
                cursor: 'pointer',
              }}
            >
              <X size={20} />
            </button>

            <h2 style={{ fontSize: '1.375rem', fontWeight: 700, color: '#f8fafc', marginBottom: '0.5rem' }}>
              {selectedScan.product_name || 'Scan Details'}
            </h2>
            <div style={{ color: '#94a3b8', fontSize: '0.8125rem', marginBottom: '1.25rem' }}>
              Analyzed on {new Date(selectedScan.created_at || selectedScan.createdAt || '').toLocaleString()}
            </div>

            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
                gap: '0.75rem',
                marginBottom: '1.5rem',
                background: 'rgba(30, 41, 59, 0.5)',
                padding: '1rem',
                borderRadius: '8px',
              }}
            >
              <div>
                <div style={{ fontSize: '0.75rem', color: '#64748b' }}>Safety Score</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#f8fafc' }}>
                  {selectedScan.overall_score.toFixed(1)} / 10
                </div>
              </div>
              <div>
                <div style={{ fontSize: '0.75rem', color: '#64748b' }}>Risk Level</div>
                <div style={{ fontSize: '1.125rem', fontWeight: 600, color: getRiskBadgeColor(selectedScan.overall_risk).text }}>
                  {selectedScan.overall_risk}
                </div>
              </div>
              <div>
                <div style={{ fontSize: '0.75rem', color: '#64748b' }}>Total Ingredients</div>
                <div style={{ fontSize: '1.125rem', fontWeight: 600, color: '#e2e8f0' }}>
                  {selectedScan.ingredients.length}
                </div>
              </div>
            </div>

            <h4 style={{ fontSize: '0.9375rem', fontWeight: 600, color: '#cbd5e1', marginBottom: '0.625rem' }}>
              Analyzed Ingredients ({selectedScan.ingredients.length})
            </h4>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.375rem', marginBottom: '1.5rem' }}>
              {selectedScan.ingredients.map((ing, idx) => (
                <span
                  key={idx}
                  style={{
                    padding: '0.25rem 0.625rem',
                    borderRadius: '6px',
                    fontSize: '0.8125rem',
                    background: 'rgba(30, 41, 59, 0.8)',
                    color: '#e2e8f0',
                    border: '1px solid rgba(255, 255, 255, 0.1)',
                  }}
                >
                  {ing}
                </span>
              ))}
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
              <button
                onClick={() => handleDeleteScan(selectedScan.id)}
                className="btn"
                style={{ background: 'rgba(239, 68, 68, 0.15)', color: '#ef4444', border: '1px solid rgba(239, 68, 68, 0.3)' }}
              >
                <Trash2 size={14} /> Delete Scan
              </button>
              <button onClick={() => setSelectedScan(null)} className="btn btn-secondary">
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
