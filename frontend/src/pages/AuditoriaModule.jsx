import React, { useState, useEffect } from 'react';
import { getStats, getResultado, getRelatorioPdf } from '../services/api';

const NIVEL_COLORS = {
  CRITICO: '#ff4757', ALTO: '#ff6b35', MEDIO: '#ffb703', BAIXO: '#00c47a',
};

const AuditoriaModule = () => {
  const [auditorias, setAuditorias]   = useState([]);
  const [loading, setLoading]         = useState(true);
  const [erro, setErro]               = useState('');
  const [selected, setSelected]       = useState(null);
  const [detalhe, setDetalhe]         = useState(null);
  const [loadingDet, setLoadingDet]   = useState(false);
  const [downloadingId, setDownloading] = useState(null);

  useEffect(() => {
    getStats()
      .then(res => {
        // Suporta campos 'auditorias', 'resultados', ou array direto
        const data = res.data?.auditorias || res.data?.resultados || res.data?.items || [];
        setAuditorias(Array.isArray(data) ? data : []);
      })
      .catch(() => setErro('Falha ao carregar auditorias.'))
      .finally(() => setLoading(false));
  }, []);

  const handleSelectRow = async (auditoria) => {
    setSelected(auditoria);
    setDetalhe(null);
    const id = auditoria.id || auditoria.auditoria_id;
    if (!id) return;
    setLoadingDet(true);
    try {
      const res = await getResultado(id);
      setDetalhe(res.data);
    } catch {
      setDetalhe({ erro: 'Não foi possível carregar o detalhe.' });
    } finally {
      setLoadingDet(false);
    }
  };

  const handleExport = async (auditoria, e) => {
    e.stopPropagation();
    const id = auditoria.id || auditoria.auditoria_id;
    if (!id) return;
    setDownloading(id);
    try {
      await getRelatorioPdf(id);
    } catch {
      alert('Falha ao baixar o relatório PDF.');
    } finally {
      setDownloading(null);
    }
  };

  return (
    <div style={{ fontFamily: 'IBM Plex Sans, sans-serif' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
        <div>
          <h2 style={{ color: '#fff', margin: 0, fontSize: '1.25rem', fontWeight: 700 }}>Carteira de Auditorias</h2>
          <p style={{ color: '#4a6b8a', fontSize: '0.75rem', margin: '0.25rem 0 0', fontFamily: 'IBM Plex Mono, monospace' }}>
            {loading ? 'Carregando...' : `${auditorias.length} registros · Pipeline HORIZON-BLUE ONE`}
          </p>
        </div>
      </div>

      {erro && (
        <div style={{ padding: '0.75rem 1rem', background: 'rgba(255,71,87,0.1)', border: '1px solid rgba(255,71,87,0.3)', borderRadius: 6, color: '#ff6b7a', fontSize: '0.8rem', marginBottom: '1rem' }}>
          {erro}
        </div>
      )}

      {/* Tabela */}
      <div style={{ background: '#020f1e', border: '1px solid rgba(0,196,255,0.1)', borderRadius: 8, overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
          <thead>
            <tr style={{ background: 'rgba(0,196,255,0.04)', borderBottom: '1px solid rgba(0,196,255,0.1)' }}>
              {['CONTRIBUINTE', 'ATIVIDADE', 'NFA-e', 'VALOR', 'SCORE', 'NÍVEL', 'AÇÕES'].map(h => (
                <th key={h} style={{ padding: '0.75rem 1rem', textAlign: 'left', color: '#4a6b8a', fontSize: '0.65rem', letterSpacing: '0.15em', fontFamily: 'IBM Plex Mono, monospace', fontWeight: 600 }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} style={{ padding: '2rem', textAlign: 'center', color: '#4a6b8a', fontFamily: 'IBM Plex Mono, monospace' }}>CARREGANDO AUDITORIAS...</td></tr>
            ) : auditorias.length === 0 ? (
              <tr><td colSpan={7} style={{ padding: '2rem', textAlign: 'center', color: '#4a6b8a', fontFamily: 'IBM Plex Mono, monospace' }}>NENHUMA AUDITORIA ENCONTRADA</td></tr>
            ) : auditorias.map((a, i) => {
              const nivel = a.nivel || a.nivel_risco || 'BAIXO';
              const isSelected = selected?.id === a.id;
              return (
                <tr key={a.id || i}
                  onClick={() => handleSelectRow(a)}
                  style={{
                    borderBottom: '1px solid rgba(0,196,255,0.05)',
                    background: isSelected ? 'rgba(0,196,255,0.06)' : i % 2 === 0 ? 'transparent' : 'rgba(0,0,0,0.2)',
                    cursor: 'pointer', transition: 'background 0.1s',
                  }}
                >
                  <td style={{ padding: '0.75rem 1rem', color: '#e0f4ff' }}>
                    <div>{a.contribuinte || a.nome || '—'}</div>
                    <div style={{ fontSize: '0.65rem', color: '#4a6b8a', fontFamily: 'IBM Plex Mono, monospace' }}>{a.cpf_anonimo || a.cpf || ''}</div>
                  </td>
                  <td style={{ padding: '0.75rem 1rem', color: '#7bafc4' }}>{a.atividade || a.produto || '—'}</td>
                  <td style={{ padding: '0.75rem 1rem', color: '#7bafc4', fontFamily: 'IBM Plex Mono, monospace' }}>{a.total_nfae || a.nfae || '—'}</td>
                  <td style={{ padding: '0.75rem 1rem', color: '#e0f4ff' }}>
                    {a.valor ? `R$ ${Number(a.valor).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}` : '—'}
                  </td>
                  <td style={{ padding: '0.75rem 1rem', color: '#fff', fontFamily: 'IBM Plex Mono, monospace', fontWeight: 700 }}>{a.score ?? '—'}</td>
                  <td style={{ padding: '0.75rem 1rem' }}>
                    <span style={{
                      padding: '0.2rem 0.5rem', borderRadius: 3, fontSize: '0.65rem', fontWeight: 700,
                      background: `${NIVEL_COLORS[nivel]}20`, border: `1px solid ${NIVEL_COLORS[nivel]}50`,
                      color: NIVEL_COLORS[nivel], fontFamily: 'IBM Plex Mono, monospace',
                    }}>
                      {nivel}
                    </span>
                  </td>
                  <td style={{ padding: '0.75rem 1rem' }}>
                    <button
                      onClick={e => handleExport(a, e)}
                      disabled={downloadingId === (a.id || a.auditoria_id)}
                      style={{
                        padding: '0.3rem 0.6rem', background: 'rgba(0,196,255,0.08)',
                        border: '1px solid rgba(0,196,255,0.25)', borderRadius: 3,
                        color: '#00c4ff', fontSize: '0.65rem', cursor: 'pointer', letterSpacing: '0.1em',
                        fontFamily: 'IBM Plex Mono, monospace',
                      }}
                    >
                      {downloadingId === (a.id || a.auditoria_id) ? '...' : 'PDF'}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Painel de detalhe */}
      {selected && (
        <div style={{ marginTop: '1.5rem', background: '#020f1e', border: '1px solid rgba(0,196,255,0.1)', borderRadius: 8, padding: '1.25rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h3 style={{ color: '#fff', margin: 0, fontSize: '1rem' }}>
              Detalhe — {selected.contribuinte || selected.nome}
            </h3>
            <button onClick={() => setSelected(null)} style={{ background: 'none', border: 'none', color: '#4a6b8a', cursor: 'pointer', fontSize: '1rem' }}>×</button>
          </div>

          {loadingDet ? (
            <div style={{ color: '#4a6b8a', fontFamily: 'IBM Plex Mono, monospace', fontSize: '0.8rem' }}>CARREGANDO RESULTADO...</div>
          ) : detalhe ? (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1rem' }}>
              {Object.entries(detalhe).filter(([k]) => !['id', 'raw'].includes(k)).slice(0, 12).map(([key, val]) => (
                <div key={key}>
                  <div style={{ fontSize: '0.6rem', color: '#4a6b8a', letterSpacing: '0.15em', fontFamily: 'IBM Plex Mono, monospace', marginBottom: '0.2rem' }}>{key.toUpperCase()}</div>
                  <div style={{ color: '#e0f4ff', fontSize: '0.8rem', wordBreak: 'break-all' }}>
                    {typeof val === 'object' ? JSON.stringify(val) : String(val ?? '—')}
                  </div>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
};

export default AuditoriaModule;
