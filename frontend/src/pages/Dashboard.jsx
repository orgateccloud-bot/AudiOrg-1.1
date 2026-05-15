import React, { useState, useEffect, lazy, Suspense } from 'react';
import { Routes, Route, Link, useLocation, useNavigate } from 'react-router-dom';
import { getStats, getRelatorioPdf } from '../services/api';

// Sub-módulos carregados via lazy
const AuditoriaModule = lazy(() => import('./AuditoriaModule'));
const UploadNFA       = lazy(() => import('./UploadNFA'));

// ── Ícones inline simples (sem dependência externa) ──────────────────────────
const Icon = ({ d, size = 16 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d={d} />
  </svg>
);

const ICONS = {
  dashboard: 'M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z',
  upload:    'M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12',
  list:      'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2',
  agents:    'M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2M9 11a4 4 0 100-8 4 4 0 000 8M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75',
  shield:    'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z',
  hash:      'M4 9h16M4 15h16M10 3L8 21M16 3l-2 18',
  logout:    'M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9',
  alert:     'M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0zM12 9v4M12 17h.01',
};

// ── Navegação do sidebar ─────────────────────────────────────────────────────
const NAV_SECTIONS = [
  {
    label: 'OPERAÇÃO',
    items: [
      { icon: 'dashboard', label: 'Centro de Comando', to: '/dashboard' },
      { icon: 'upload',    label: 'Nova Auditoria',    to: '/dashboard/upload' },
      { icon: 'list',      label: 'Auditorias',        to: '/dashboard/auditorias' },
    ],
  },
  {
    label: 'INTELIGÊNCIA',
    items: [
      { icon: 'agents', label: 'Squad A-07 / A-08',    to: '/dashboard/squad' },
      { icon: 'shield', label: 'Detectores forenses',  to: '/dashboard/detectores' },
      { icon: 'list',   label: 'Laudos técnicos',      to: '/dashboard/laudos' },
      { icon: 'hash',   label: 'Trilha SHA-256',        to: '/dashboard/trilha' },
    ],
  },
];

// ── Dashboard principal ──────────────────────────────────────────────────────
const Dashboard = () => {
  const navigate  = useNavigate();
  const location  = useLocation();
  const [stats, setStats]     = useState(null);
  const [loading, setLoading] = useState(true);
  const [erro, setErro]       = useState('');

  useEffect(() => {
    getStats()
      .then(res => setStats(res.data))
      .catch(() => setErro('Falha ao carregar estatísticas — modo offline'))
      .finally(() => setLoading(false));
  }, []);

  const handleLogout = () => {
    localStorage.removeItem('orgatec_token');
    navigate('/login');
  };

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden', background: '#020c18', fontFamily: 'IBM Plex Sans, sans-serif' }}>

      {/* ── Sidebar ────────────────────────────────────────────────────────── */}
      <aside style={{
        width: 240, background: '#020f1e', borderRight: '1px solid rgba(0,196,255,0.1)',
        display: 'flex', flexDirection: 'column', padding: '1.5rem 1rem', flexShrink: 0,
      }}>
        {/* Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '2rem', padding: '0 0.5rem' }}>
          <div style={{
            width: 32, height: 32, borderRadius: '50%', flexShrink: 0,
            background: 'radial-gradient(circle at 35% 35%, #4fc3f7, #0277bd, #002f6c)',
            boxShadow: '0 0 12px rgba(0,196,255,0.3)',
          }} />
          <div>
            <div style={{ fontSize: '0.8rem', fontWeight: 800, color: '#fff', letterSpacing: '0.15em' }}>ORGATEC</div>
            <div style={{ fontSize: '0.55rem', color: '#00c4ff', letterSpacing: '0.3em', fontFamily: 'IBM Plex Mono, monospace' }}>SOVEREIGN v8.0</div>
          </div>
        </div>

        {/* Nav sections */}
        <nav style={{ flex: 1, overflowY: 'auto' }}>
          {NAV_SECTIONS.map(section => (
            <div key={section.label} style={{ marginBottom: '1.5rem' }}>
              <div style={{ fontSize: '0.55rem', color: '#2a4a5e', letterSpacing: '0.3em', fontFamily: 'IBM Plex Mono, monospace', padding: '0 0.5rem', marginBottom: '0.5rem' }}>
                {section.label}
              </div>
              {section.items.map(item => {
                const active = location.pathname === item.to || (item.to !== '/dashboard' && location.pathname.startsWith(item.to));
                return (
                  <Link key={item.to} to={item.to} style={{ textDecoration: 'none' }}>
                    <div style={{
                      display: 'flex', alignItems: 'center', gap: '0.6rem',
                      padding: '0.6rem 0.75rem', borderRadius: 6, marginBottom: '0.15rem',
                      background: active ? 'rgba(0,196,255,0.1)' : 'transparent',
                      border: active ? '1px solid rgba(0,196,255,0.2)' : '1px solid transparent',
                      color: active ? '#00c4ff' : '#4a6b8a',
                      fontSize: '0.8rem', cursor: 'pointer', transition: 'all 0.15s',
                    }}>
                      <Icon d={ICONS[item.icon]} size={14} />
                      <span>{item.label}</span>
                    </div>
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>

        {/* Logout */}
        <button onClick={handleLogout} style={{
          display: 'flex', alignItems: 'center', gap: '0.6rem',
          padding: '0.6rem 0.75rem', background: 'none', border: 'none',
          color: '#2a4a5e', fontSize: '0.8rem', cursor: 'pointer',
          width: '100%', borderRadius: 6,
        }}>
          <Icon d={ICONS.logout} size={14} />
          <span>Sair do Sistema</span>
        </button>
      </aside>

      {/* ── Conteúdo principal ────────────────────────────────────────────── */}
      <main style={{ flex: 1, overflowY: 'auto', padding: '2rem' }}>
        <Suspense fallback={<div style={{ color: '#4a6b8a', fontFamily: 'IBM Plex Mono, monospace', fontSize: '0.8rem' }}>CARREGANDO MÓDULO...</div>}>
          <Routes>
            <Route path="/"           element={<HomeModule stats={stats} loading={loading} erro={erro} />} />
            <Route path="/upload"     element={<UploadNFA />} />
            <Route path="/auditorias" element={<AuditoriaModule />} />
            <Route path="/squad"      element={<SquadModule />} />
            <Route path="/detectores" element={<DetectoresModule />} />
            <Route path="/laudos"     element={<AuditoriaModule />} />
            <Route path="/trilha"     element={<TrilhaModule />} />
          </Routes>
        </Suspense>
      </main>
    </div>
  );
};

// ── Centro de Comando ────────────────────────────────────────────────────────
const HomeModule = ({ stats, loading, erro }) => {
  const kpis = [
    { label: 'LAUDOS EMITIDOS', value: stats?.total_laudos ?? stats?.laudos_emitidos ?? '—', color: '#00c4ff', sub: 'total acumulado' },
    { label: 'EM CURSO',        value: stats?.em_curso ?? stats?.auditorias_ativas ?? '—',   color: '#00c47a', sub: 'aguardando resultado' },
    { label: 'VOLUME APURADO',  value: stats?.volume_funrural ? `R$ ${(stats.volume_funrural/1e6).toFixed(1)}M` : '—', color: '#ffb703', sub: 'FUNRURAL apurado' },
    { label: 'ALERTAS CRÍTICOS',value: stats?.alertas_criticos ?? stats?.alertas ?? '—',     color: '#ff4757', sub: 'A-07 detectados' },
  ];

  return (
    <div>
      <div style={{ marginBottom: '2rem' }}>
        <h1 style={{ fontSize: '1.75rem', fontWeight: 800, color: '#fff', margin: 0 }}>Centro de Comando.</h1>
        <p style={{ fontSize: '0.8rem', color: '#4a6b8a', marginTop: '0.25rem', fontFamily: 'IBM Plex Mono, monospace' }}>
          {loading ? 'Sincronizando com a API...' : erro ? erro : `Pipeline HORIZON-BLUE ONE · ${new Date().toLocaleDateString('pt-BR')}`}
        </p>
      </div>

      {/* KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', marginBottom: '2rem' }}>
        {kpis.map(kpi => (
          <div key={kpi.label} style={{
            padding: '1.25rem', background: '#020f1e', border: '1px solid rgba(0,196,255,0.1)',
            borderRadius: 8, borderTop: `2px solid ${kpi.color}`,
          }}>
            <div style={{ fontSize: '0.6rem', color: '#4a6b8a', letterSpacing: '0.2em', fontFamily: 'IBM Plex Mono, monospace', marginBottom: '0.5rem' }}>{kpi.label}</div>
            <div style={{ fontSize: '1.75rem', fontWeight: 800, color: '#fff' }}>{loading ? '···' : kpi.value}</div>
            <div style={{ fontSize: '0.65rem', color: '#2a4a5e', marginTop: '0.25rem' }}>{kpi.sub}</div>
          </div>
        ))}
      </div>

      {/* Pipeline status */}
      <div style={{ background: '#020f1e', border: '1px solid rgba(0,196,255,0.1)', borderRadius: 8, padding: '1.25rem' }}>
        <div style={{ fontSize: '0.65rem', color: '#4a6b8a', letterSpacing: '0.2em', fontFamily: 'IBM Plex Mono, monospace', marginBottom: '1rem' }}>
          PIPELINE · HORIZON-BLUE ONE
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
          {['RE-1', 'XGBoost', 'F1-F6', 'A-07', 'A-08'].map((step, i) => (
            <React.Fragment key={step}>
              <div style={{
                padding: '0.4rem 0.75rem', background: 'rgba(0,196,255,0.08)',
                border: '1px solid rgba(0,196,255,0.2)', borderRadius: 4,
                color: '#00c4ff', fontSize: '0.75rem', fontFamily: 'IBM Plex Mono, monospace',
              }}>
                {step}
              </div>
              {i < 4 && <div style={{ color: '#2a4a5e', fontSize: '0.8rem' }}>→</div>}
            </React.Fragment>
          ))}
          <div style={{ marginLeft: 'auto', fontSize: '0.65rem', color: '#4a6b8a', fontFamily: 'IBM Plex Mono, monospace' }}>
            @Delta ATIVO · SHA-256 · v8.0.0
          </div>
        </div>
      </div>
    </div>
  );
};

// ── Squad A-07 / A-08 ────────────────────────────────────────────────────────
const SquadModule = () => (
  <div>
    <h2 style={{ color: '#fff', marginBottom: '1.5rem' }}>Squad A-07 / A-08</h2>
    {[
      { id: 'A-07', name: 'Auditoria Assurance', type: 'Determinístico', status: 'ATIVO', desc: '5 detectores forenses: CARROSSEL, SMURFING, FANTASMA, DEVOLUÇÃO, TEMPORAL' },
      { id: 'A-08', name: 'Auditor NFA-e',       type: 'Claude Sonnet',  status: 'ATIVO', desc: 'Análise qualitativa LLM + Protocolo @Delta anonimização + fallback determinístico' },
    ].map(agent => (
      <div key={agent.id} style={{
        background: '#020f1e', border: '1px solid rgba(0,196,255,0.15)', borderRadius: 8,
        padding: '1.25rem', marginBottom: '1rem', display: 'flex', alignItems: 'flex-start', gap: '1rem',
      }}>
        <div style={{
          width: 48, height: 48, borderRadius: '50%', flexShrink: 0,
          background: 'rgba(0,196,255,0.1)', border: '1px solid rgba(0,196,255,0.3)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: '#00c4ff', fontFamily: 'IBM Plex Mono, monospace', fontSize: '0.65rem', fontWeight: 700,
        }}>
          {agent.id}
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.25rem' }}>
            <span style={{ color: '#fff', fontWeight: 600 }}>{agent.name}</span>
            <span style={{ padding: '0.15rem 0.5rem', background: 'rgba(0,196,127,0.1)', border: '1px solid rgba(0,196,127,0.3)', borderRadius: 3, color: '#00c47a', fontSize: '0.6rem', fontFamily: 'IBM Plex Mono, monospace' }}>{agent.status}</span>
            <span style={{ color: '#4a6b8a', fontSize: '0.7rem' }}>{agent.type}</span>
          </div>
          <p style={{ color: '#7bafc4', fontSize: '0.8rem', margin: 0 }}>{agent.desc}</p>
        </div>
      </div>
    ))}
    <div style={{ padding: '1rem', background: 'rgba(0,196,255,0.04)', border: '1px solid rgba(0,196,255,0.1)', borderRadius: 6, color: '#4a6b8a', fontSize: '0.7rem', fontFamily: 'IBM Plex Mono, monospace' }}>
      26 agentes em standby (a00–a27) · Pipeline: RE-1 → XGBoost → F1-F6 → A-07 → A-08
    </div>
  </div>
);

// ── Detectores Forenses ──────────────────────────────────────────────────────
const DetectoresModule = () => (
  <div>
    <h2 style={{ color: '#fff', marginBottom: '1.5rem' }}>Detectores Forenses A-07</h2>
    {[
      { id: 'CARROSSEL_FISCAL',    desc: 'Mesmo CNPJ como emitente E destinatário na mesma operação' },
      { id: 'SMURFING_RURAL',      desc: 'Múltiplas notas abaixo do limiar de tributação no mesmo dia' },
      { id: 'FORNECEDOR_FANTASMA', desc: 'Fornecedor com volume alto sem histórico recorrente' },
      { id: 'DEVOLUCAO_POSTERIOR', desc: 'Nota de devolução emitida muito depois da original' },
      { id: 'ANOMALIA_TEMPORAL',   desc: 'Concentração de emissões em finais de semana ou feriados' },
    ].map(d => (
      <div key={d.id} style={{
        background: '#020f1e', border: '1px solid rgba(0,196,255,0.1)', borderRadius: 6,
        padding: '1rem', marginBottom: '0.75rem', display: 'flex', gap: '1rem', alignItems: 'center',
      }}>
        <div style={{ color: '#00c4ff', fontFamily: 'IBM Plex Mono, monospace', fontSize: '0.7rem', minWidth: 180 }}>{d.id}</div>
        <div style={{ color: '#7bafc4', fontSize: '0.8rem' }}>{d.desc}</div>
        <div style={{ marginLeft: 'auto', color: '#00c47a', fontSize: '0.65rem', fontFamily: 'IBM Plex Mono, monospace' }}>DETERMINÍSTICO</div>
      </div>
    ))}
  </div>
);

// ── Trilha SHA-256 ────────────────────────────────────────────────────────────
const TrilhaModule = () => (
  <div>
    <h2 style={{ color: '#fff', marginBottom: '0.5rem' }}>Trilha de Auditoria SHA-256</h2>
    <p style={{ color: '#4a6b8a', fontSize: '0.8rem', marginBottom: '1.5rem', fontFamily: 'IBM Plex Mono, monospace' }}>
      Cada AgentResult possui audit_hash SHA-256 calculado em tempo real. Imutável e verificável.
    </p>
    <div style={{ background: '#020f1e', border: '1px solid rgba(0,196,255,0.1)', borderRadius: 8, padding: '1.25rem' }}>
      <div style={{ color: '#4a6b8a', fontSize: '0.65rem', letterSpacing: '0.2em', fontFamily: 'IBM Plex Mono, monospace', marginBottom: '0.75rem' }}>
        ALGORITMO · SHA-256 · PROTOCOLO @DELTA ATIVO
      </div>
      <p style={{ color: '#7bafc4', fontSize: '0.8rem', lineHeight: 1.6 }}>
        Antes de enviar dados ao LLM, <code style={{ color: '#00c4ff', background: 'rgba(0,196,255,0.1)', padding: '0.1rem 0.3rem', borderRadius: 3 }}>privacy.py</code> substitui CPF/CNPJ/nomes por tokens @DELTA-001, @PESSOA-001, @EMPRESA-001. O mapa de reversão é aplicado na resposta. Nenhum dado pessoal trafega para LLMs externos.
      </p>
    </div>
  </div>
);

export default Dashboard;
