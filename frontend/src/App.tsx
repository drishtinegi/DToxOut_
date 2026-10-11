import { useState, useEffect } from 'react';
import { Header } from './components/Header';
import { AuthModal } from './components/AuthModal';
import { IngredientInputStep } from './components/IngredientInputStep';
import { IngredientReviewStep } from './components/IngredientReviewStep';
import { AnalysisResultStep } from './components/AnalysisResultStep';
import { ScanHistoryView } from './components/ScanHistoryView';
import { api, authStorage } from './services/api';
import type { User, OCRPrepareResponse, ScanResponse } from './types';

export function App() {
  const [user, setUser] = useState<User | null>(authStorage.getUser());
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
  const [currentView, setCurrentView] = useState<'analyze' | 'history'>('analyze');

  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [productName, setProductName] = useState('');
  const [prepareData, setPrepareData] = useState<OCRPrepareResponse | null>(null);
  const [scanResult, setScanResult] = useState<ScanResponse | null>(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Check current auth status on mount
    if (authStorage.getToken()) {
      api
        .getCurrentUser()
        .then((u) => setUser(u))
        .catch(() => {
          authStorage.removeToken();
          setUser(null);
        });
    }

    const handleAuthExpired = () => {
      setUser(null);
      setIsAuthModalOpen(true);
      setError('Your authentication session has expired. Please sign in again.');
    };

    window.addEventListener('dtoxout_auth_expired', handleAuthExpired);
    return () => {
      window.removeEventListener('dtoxout_auth_expired', handleAuthExpired);
    };
  }, []);

  const ensureAuthenticated = async (): Promise<boolean> => {
    if (user && authStorage.getToken()) {
      return true;
    }
    // Attempt Quick Demo Login if not logged in
    try {
      const authRes = await api.quickDemoLogin();
      if (authRes.user) {
        setUser(authRes.user);
      } else {
        const u = await api.getCurrentUser();
        setUser(u);
      }
      return true;
    } catch {
      setIsAuthModalOpen(true);
      return false;
    }
  };

  const handlePrepare = async (pName: string, text: string) => {
    setError(null);
    setLoading(true);

    const isAuth = await ensureAuthenticated();
    if (!isAuth) {
      setLoading(false);
      return;
    }

    setProductName(pName);

    try {
      const data = await api.prepareText(text);
      setPrepareData(data);
      setStep(2);
      setCurrentView('analyze');
    } catch (err: any) {
      setError(err?.message || 'An unexpected error occurred while preparing text.');
    } finally {
      setLoading(false);
    }
  };

  const handleConfirmAnalysis = async (confirmedTerms: string[]) => {
    setError(null);
    setLoading(true);

    const isAuth = await ensureAuthenticated();
    if (!isAuth) {
      setLoading(false);
      return;
    }

    try {
      const result = await api.analyzeIngredients(confirmedTerms);
      setScanResult(result);
      setStep(3);
      setCurrentView('analyze');
    } catch (err: any) {
      setError(err?.message || 'An unexpected error occurred during safety analysis.');
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    authStorage.removeToken();
    setUser(null);
    setStep(1);
    setCurrentView('analyze');
  };

  return (
    <div>
      <Header
        user={user}
        currentView={currentView}
        onNavigate={(view) => {
          setCurrentView(view);
          setError(null);
        }}
        onOpenAuth={() => setIsAuthModalOpen(true)}
        onLogout={handleLogout}
      />

      <main className="app-container" style={{ marginTop: '1.5rem', marginBottom: '3rem' }}>
        {currentView === 'history' ? (
          <ScanHistoryView
            onNewAnalysis={() => {
              setCurrentView('analyze');
              setStep(1);
              setProductName('');
              setPrepareData(null);
              setScanResult(null);
              setError(null);
            }}
          />
        ) : (
          <>
            {step === 1 && (
              <IngredientInputStep
                onPrepare={handlePrepare}
                loading={loading}
                error={error}
              />
            )}

            {step === 2 && prepareData && (
              <IngredientReviewStep
                productName={productName}
                prepareData={prepareData}
                onConfirm={handleConfirmAnalysis}
                onBack={() => setStep(1)}
                loading={loading}
                error={error}
              />
            )}

            {step === 3 && scanResult && (
              <AnalysisResultStep
                productName={productName}
                result={scanResult}
                onEdit={() => setStep(2)}
                onNewAnalysis={() => {
                  setStep(1);
                  setProductName('');
                  setPrepareData(null);
                  setScanResult(null);
                  setError(null);
                }}
              />
            )}
          </>
        )}
      </main>

      <AuthModal
        isOpen={isAuthModalOpen}
        onClose={() => setIsAuthModalOpen(false)}
        onSuccess={(u) => {
          setUser(u);
          setIsAuthModalOpen(false);
        }}
      />
    </div>
  );
}

export default App;
