import React from 'react';
import { ShieldCheck, User as UserIcon, LogOut, Key, History, Sparkles } from 'lucide-react';
import type { User } from '../types';

interface HeaderProps {
  user: User | null;
  currentView: 'analyze' | 'history';
  onNavigate: (view: 'analyze' | 'history') => void;
  onOpenAuth: () => void;
  onLogout: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  user,
  currentView,
  onNavigate,
  onOpenAuth,
  onLogout,
}) => {
  return (
    <header className="app-header">
      <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem' }}>
        <a href="/" className="brand-logo" onClick={(e) => { e.preventDefault(); onNavigate('analyze'); }}>
          <ShieldCheck className="w-8 h-8 text-sky-400" size={32} color="#0ea5e9" />
          <div>
            <div className="brand-title">DToxOut</div>
            <div style={{ fontSize: '0.75rem', color: '#94a3b8', marginTop: '-4px' }}>
              Cosmetic Ingredient Safety Platform
            </div>
          </div>
        </a>

        {user && (
          <nav style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              onClick={() => onNavigate('analyze')}
              style={{
                background: currentView === 'analyze' ? 'rgba(14, 165, 233, 0.15)' : 'transparent',
                color: currentView === 'analyze' ? '#38bdf8' : '#94a3b8',
                border: 'none',
                padding: '0.4rem 0.75rem',
                borderRadius: '6px',
                fontWeight: 600,
                fontSize: '0.8125rem',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '0.375rem',
              }}
            >
              <Sparkles size={14} />
              <span>Analyze</span>
            </button>
            <button
              onClick={() => onNavigate('history')}
              style={{
                background: currentView === 'history' ? 'rgba(14, 165, 233, 0.15)' : 'transparent',
                color: currentView === 'history' ? '#38bdf8' : '#94a3b8',
                border: 'none',
                padding: '0.4rem 0.75rem',
                borderRadius: '6px',
                fontWeight: 600,
                fontSize: '0.8125rem',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '0.375rem',
              }}
            >
              <History size={14} />
              <span>Scan History</span>
            </button>
          </nav>
        )}
      </div>

      <div className="header-right">
        <span
          className="badge"
          style={{
            background: 'rgba(14, 165, 233, 0.1)',
            color: '#38bdf8',
            border: '1px solid rgba(14, 165, 233, 0.25)',
            textTransform: 'none',
            fontSize: '0.75rem',
            fontWeight: 500,
          }}
        >
          Informational Only
        </span>

        {user ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                fontSize: '0.875rem',
                color: '#e2e8f0',
              }}
            >
              <UserIcon size={18} color="#0ea5e9" />
              <span>{user.username}</span>
            </div>
            <button
              onClick={onLogout}
              className="btn btn-secondary"
              style={{ padding: '0.4rem 0.75rem', fontSize: '0.8125rem' }}
              title="Log Out"
            >
              <LogOut size={14} />
              <span>Logout</span>
            </button>
          </div>
        ) : (
          <button
            onClick={onOpenAuth}
            className="btn btn-primary"
            style={{ padding: '0.4rem 0.875rem', fontSize: '0.8125rem' }}
          >
            <Key size={14} />
            <span>Sign In / Quick Access</span>
          </button>
        )}
      </div>
    </header>
  );
};
