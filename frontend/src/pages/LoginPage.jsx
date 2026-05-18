import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { login } from '../services/api';

const LoginPage = () => {
  const navigate = useNavigate();
  const [email, setEmail]       = useState('');
  const [senha, setSenha]       = useState('');
  const [loading, setLoading]   = useState(false);
  const [erro, setErro]         = useState('');

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    setErro('');
    try {
      const res = await login(email, senha);
      const token = res.data?.access_token || res.data?.token;
      if (token) {
        localStorage.setItem('orgatec_token', token);
        navigate('/dashboard');
      } else {
        setErro('Resposta inválida do servidor.');
      }
    } catch (err) {
      const msg = err.response?.data?.detail || err.response?.data?.message || 'Credenciais inválidas.';
      setErro(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', background: '#020c18',
      fontFamily: 'IBM Plex Sans, sans-serif',
    }}>
      {/* Coluna esquerda — Manifesto */}
      <div style={{
        flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center',
        padding: '3rem 4rem', background: 'rgba(0,12,24,0.95)',
        borderRight: '1px solid rgba(0,196,255,0.1)',
        '@media (max-width: 768px)': { display: 'none' },
      }}>
        <div style={{ maxWidth: 400 }}>
          <div style={{
            width: 56, height: 56, borderRadius: '50%', marginBottom: '2rem',
            background: 'radial-gradient(circle at 35% 35%, #4fc3f7, #0277bd, #002f6c)',
            boxShadow: '0 0 30px rgba(0,196,255,0.3)',
          }} />
          <h1 style={{ fontSize: '1.75rem', fontWeight: 800, color: '#fff', marginBottom: '0.5rem', letterSpacing: '0.05em' }}>
            ORGATEC
          </h1>
          <p style={{ fontSize: '0.7rem', color: '#00c4ff', letterSpacing: '0.3em', marginBottom: '2.5rem' }}>
            AUDITORIA FISCAL SOBERANA
          </p>

          <blockquote style={{ borderLeft: '2px solid rgba(0,196,255,0.3)', paddingLeft: '1rem', marginBottom: '2rem' }}>
            <p style={{ fontSize: '0.95rem', color: '#b0cfe0', lineHeight: 1.7, fontStyle: 'italic' }}>
              "Toda operação fiscal é auditável. Todo dado é rastreável. Toda decisão é justificada."
            </p>
          </blockquote>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {[
              { label: 'Pipeline', value: 'RE-1 → XGBoost → F1-F6 → A-07 → A-08' },
              { label: 'Protocolo', value: '@Delta — anonimização CPF/CNPJ' },
              { label: 'Trilha', value: 'SHA-256 íntegra em cada laudo' },
              { label: 'Score', value: '9.0/10 · Build a9f4b2e' },
            ].map(({ label, value }) => (
              <div key={label} style={{ display: 'flex', gap: '0.75rem', fontSize: '0.75rem' }}>
                <span style={{ color: '#4a6b8a', minWidth: 72, fontFamily: 'IBM Plex Mono, monospace' }}>{label}</span>
                <span style={{ color: '#7bafc4' }}>{value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Coluna direita — Formulário */}
      <div style={{
        width: 480, display: 'flex', flexDirection: 'column', justifyContent: 'center',
        padding: '3rem 3rem', background: '#020f1e',
      }}>
        <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: '#fff', marginBottom: '0.25rem' }}>
          Acesso ao Sistema
        </h2>
        <p style={{ fontSize: '0.8rem', color: '#4a6b8a', marginBottom: '2rem', fontFamily: 'IBM Plex Mono, monospace' }}>
          HORIZON-BLUE ONE · v8.0.0
        </p>

        <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.7rem', color: '#4a6b8a', letterSpacing: '0.15em', marginBottom: '0.4rem', fontFamily: 'IBM Plex Mono, monospace' }}>
              E-MAIL
            </label>
            <input
              type="email" value={email} onChange={e => setEmail(e.target.value)} required
              placeholder="auditor@orgatec.com.br"
              style={{
                width: '100%', padding: '0.75rem 1rem', background: 'rgba(0,196,255,0.04)',
                border: '1px solid rgba(0,196,255,0.2)', borderRadius: 4,
                color: '#e0f4ff', fontSize: '0.875rem', outline: 'none', boxSizing: 'border-box',
                fontFamily: 'IBM Plex Sans, sans-serif',
              }}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.7rem', color: '#4a6b8a', letterSpacing: '0.15em', marginBottom: '0.4rem', fontFamily: 'IBM Plex Mono, monospace' }}>
              SENHA
            </label>
            <input
              type="password" value={senha} onChange={e => setSenha(e.target.value)} required
              placeholder="••••••••"
              style={{
                width: '100%', padding: '0.75rem 1rem', background: 'rgba(0,196,255,0.04)',
                border: '1px solid rgba(0,196,255,0.2)', borderRadius: 4,
                color: '#e0f4ff', fontSize: '0.875rem', outline: 'none', boxSizing: 'border-box',
                fontFamily: 'IBM Plex Sans, sans-serif',
              }}
            />
          </div>

          {erro && (
            <div style={{
              padding: '0.75rem 1rem', background: 'rgba(255,71,87,0.1)',
              border: '1px solid rgba(255,71,87,0.3)', borderRadius: 4,
              color: '#ff6b7a', fontSize: '0.8rem',
            }}>
              {erro}
            </div>
          )}

          <button
            type="submit" disabled={loading}
            style={{
              marginTop: '0.5rem', padding: '0.875rem', background: loading ? 'rgba(0,196,255,0.05)' : 'rgba(0,196,255,0.1)',
              border: '1px solid rgba(0,196,255,0.4)', borderRadius: 4,
              color: '#00c4ff', fontSize: '0.8rem', letterSpacing: '0.2em',
              fontFamily: 'IBM Plex Mono, monospace', cursor: loading ? 'not-allowed' : 'pointer',
              transition: 'all 0.2s',
            }}
          >
            {loading ? 'AUTENTICANDO...' : 'ENTRAR COM MFA →'}
          </button>
        </form>

        <p style={{ marginTop: '2rem', fontSize: '0.65rem', color: '#2a4a5e', textAlign: 'center', letterSpacing: '0.15em', fontFamily: 'IBM Plex Mono, monospace' }}>
          PROTOCOLO @DELTA ATIVO · DADOS PROTEGIDOS · LGPD
        </p>
      </div>
    </div>
  );
};

export default LoginPage;
