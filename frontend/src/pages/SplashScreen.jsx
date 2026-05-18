import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ping } from '../services/api';

// Sequência de boot exibida na splash
const BOOT_LINES = [
  'ORGATEC SOVEREIGN OS v8.0.0',
  'Inicializando pipeline HORIZON-BLUE ONE...',
  'RE-1 → Reclassificador fiscal rural .......... OK',
  'XGBoost Scorer (8 features SEFAZ-GO) ......... OK',
  'F1-F6 → Apuração FUNRURAL 2026 .............. OK',
  'A-07 → Auditoria Assurance (determinístico) .. OK',
  'A-08 → Auditor NFA-e (Claude Sonnet) ......... OK',
  'Protocolo @Delta (anonimização CPF/CNPJ) ..... OK',
  'Trilha SHA-256 íntegra ........................ OK',
  'Conectando à API...',
];

const SplashScreen = () => {
  const navigate = useNavigate();
  const [bootLines, setBootLines]     = useState([]);
  const [apiStatus, setApiStatus]     = useState('checking'); // 'checking' | 'online' | 'offline'
  const [showEnter, setShowEnter]     = useState(false);

  // Anima as linhas de boot uma por uma
  useEffect(() => {
    let i = 0;
    const timer = setInterval(() => {
      if (i < BOOT_LINES.length) {
        setBootLines(prev => [...prev, BOOT_LINES[i]]);
        i++;
      } else {
        clearInterval(timer);
        checkApi();
      }
    }, 220);
    return () => clearInterval(timer);
  }, []);

  const checkApi = async () => {
    try {
      await ping();
      setApiStatus('online');
    } catch {
      setApiStatus('offline');
    } finally {
      setTimeout(() => setShowEnter(true), 400);
    }
  };

  const handleEnter = () => {
    const token = localStorage.getItem('orgatec_token');
    navigate(token ? '/dashboard' : '/login');
  };

  const statusColor = apiStatus === 'online' ? '#00c47a' : apiStatus === 'offline' ? '#ff4757' : '#ffb703';
  const statusLabel = apiStatus === 'online' ? 'API ONLINE' : apiStatus === 'offline' ? 'API OFFLINE — MODO AUTÔNOMO' : 'VERIFICANDO...';

  return (
    <div style={{
      minHeight: '100vh', background: '#020c18', display: 'flex',
      flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      fontFamily: 'IBM Plex Mono, monospace', color: '#e0f4ff', position: 'relative',
      overflow: 'hidden',
    }}>
      {/* Grade de fundo */}
      <div style={{
        position: 'absolute', inset: 0,
        backgroundImage: 'linear-gradient(rgba(0,196,255,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(0,196,255,0.04) 1px, transparent 1px)',
        backgroundSize: '40px 40px',
      }} />

      {/* Logo ORB */}
      <div style={{ position: 'relative', marginBottom: '2rem', textAlign: 'center' }}>
        <div style={{
          width: 120, height: 120, borderRadius: '50%', margin: '0 auto 1rem',
          background: 'radial-gradient(circle at 35% 35%, #4fc3f7, #0277bd, #01579b, #002f6c)',
          boxShadow: '0 0 60px rgba(0,196,255,0.4), 0 0 120px rgba(0,196,255,0.15)',
          border: '2px solid rgba(0,196,255,0.3)',
        }} />
        <h1 style={{ fontSize: '2.5rem', fontWeight: 900, letterSpacing: '0.3em', color: '#fff', margin: 0 }}>
          ORGATEC
        </h1>
        <p style={{ fontSize: '0.75rem', letterSpacing: '0.4em', color: '#00c4ff', margin: '0.25rem 0 0' }}>
          AUDITORIA FISCAL SOBERANA
        </p>
        <p style={{ fontSize: '0.6rem', letterSpacing: '0.2em', color: '#4a6b8a', margin: '0.25rem 0 0' }}>
          OrgAudi · v8.0.0 — pipeline HORIZON-BLUE ONE
        </p>
      </div>

      {/* Terminal de boot */}
      <div style={{
        width: '100%', maxWidth: 560, background: 'rgba(0,12,24,0.8)',
        border: '1px solid rgba(0,196,255,0.15)', borderRadius: 8, padding: '1rem 1.5rem',
        marginBottom: '1.5rem', minHeight: 220,
      }}>
        {bootLines.map((line, i) => (
          <div key={i} style={{ fontSize: '0.7rem', lineHeight: 1.8, color: i === bootLines.length - 1 ? '#00c4ff' : '#7bafc4' }}>
            <span style={{ color: '#4a6b8a', marginRight: '0.5rem' }}>{'>'}</span>{line}
          </div>
        ))}
        {bootLines.length > 0 && (
          <span style={{ display: 'inline-block', width: 8, height: 14, background: '#00c4ff', animation: 'blink 1s infinite', verticalAlign: 'middle', marginLeft: 4 }} />
        )}
      </div>

      {/* Status da API */}
      {bootLines.length === BOOT_LINES.length && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.5rem', fontSize: '0.65rem', letterSpacing: '0.15em' }}>
          <div style={{ width: 8, height: 8, borderRadius: '50%', background: statusColor, boxShadow: `0 0 8px ${statusColor}` }} />
          <span style={{ color: statusColor }}>{statusLabel}</span>
        </div>
      )}

      {/* Botão ENTRAR */}
      {showEnter && (
        <button
          onClick={handleEnter}
          style={{
            padding: '0.875rem 2.5rem', border: '1px solid rgba(0,196,255,0.5)',
            background: 'rgba(0,196,255,0.08)', color: '#00c4ff', borderRadius: 4,
            fontFamily: 'IBM Plex Mono, monospace', fontSize: '0.8rem', letterSpacing: '0.25em',
            cursor: 'pointer', transition: 'all 0.2s',
          }}
          onMouseEnter={e => { e.target.style.background = 'rgba(0,196,255,0.18)'; e.target.style.boxShadow = '0 0 20px rgba(0,196,255,0.3)'; }}
          onMouseLeave={e => { e.target.style.background = 'rgba(0,196,255,0.08)'; e.target.style.boxShadow = 'none'; }}
        >
          ENTRAR NO SISTEMA →
        </button>
      )}

      {/* Rodapé */}
      <div style={{ position: 'absolute', bottom: '1.5rem', left: 0, right: 0, textAlign: 'center', fontSize: '0.55rem', color: '#2a4a5e', letterSpacing: '0.2em' }}>
        ORGATEC · AUDITORIA FISCAL RURAL · PROTOCOLO @DELTA ATIVO · SHA-256 ÍNTEGRA
      </div>

      <style>{`
        @keyframes blink { 0%, 100% { opacity: 1 } 50% { opacity: 0 } }
      `}</style>
    </div>
  );
};

export default SplashScreen;
