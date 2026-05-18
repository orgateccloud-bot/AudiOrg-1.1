import React, { Suspense, lazy } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';

// Lazy loading para melhor performance
const SplashScreen = lazy(() => import('./pages/SplashScreen'));
const LoginPage    = lazy(() => import('./pages/LoginPage'));
const Dashboard    = lazy(() => import('./pages/Dashboard'));

// ── Guard de autenticação ─────────────────────────────────────────────────────
const PrivateRoute = ({ children }) => {
  const token = localStorage.getItem('orgatec_token');
  return token ? children : <Navigate to="/login" replace />;
};

// ── Loading fallback (tema OrgAudi) ──────────────────────────────────────────
const LoadingFallback = () => (
  <div style={{
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    height: '100vh', background: '#020c18', color: '#00c4ff',
    fontFamily: 'IBM Plex Mono, monospace', fontSize: '0.875rem',
    letterSpacing: '0.1em',
  }}>
    CARREGANDO MÓDULO...
  </div>
);

function App() {
  return (
    <Router>
      <Suspense fallback={<LoadingFallback />}>
        <Routes>
          {/* Splash — entrada do sistema */}
          <Route path="/" element={<SplashScreen />} />

          {/* Login */}
          <Route path="/login" element={<LoginPage />} />

          {/* Dashboard protegido por token */}
          <Route
            path="/dashboard/*"
            element={
              <PrivateRoute>
                <Dashboard />
              </PrivateRoute>
            }
          />

          {/* Catch-all → splash */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </Router>
  );
}

export default App;
