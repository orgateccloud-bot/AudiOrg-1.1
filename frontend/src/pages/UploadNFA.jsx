import React, { useState, useRef, useEffect } from 'react';
import { uploadNfae, getTaskStatus } from '../services/api';

const UploadNFA = () => {
  const [clientId, setClientId]     = useState('');
  const [cabecas, setCabecas]       = useState('');
  const [cpf, setCpf]               = useState('');
  const [arquivo, setArquivo]       = useState(null);
  const [loading, setLoading]       = useState(false);
  const [taskId, setTaskId]         = useState(null);
  const [status, setStatus]         = useState(null);
  const [erro, setErro]             = useState('');
  const [sucesso, setSucesso]       = useState('');
  const fileRef                     = useRef();
  const pollRef                     = useRef();

  // Polling do status da task
  useEffect(() => {
    if (!taskId) return;
    pollRef.current = setInterval(async () => {
      try {
        const res = await getTaskStatus(taskId);
        const s = res.data;
        setStatus(s);
        if (s.status === 'concluido' || s.status === 'erro' || s.status === 'done' || s.status === 'failed') {
          clearInterval(pollRef.current);
          if (s.status === 'concluido' || s.status === 'done') {
            setSucesso(`Auditoria concluída! ID: ${s.resultado_id || taskId}`);
          } else {
            setErro(`Erro no processamento: ${s.mensagem || 'Falha desconhecida'}`);
          }
          setLoading(false);
        }
      } catch { /* continua polling */ }
    }, 2000);
    return () => clearInterval(pollRef.current);
  }, [taskId]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!clientId || !arquivo) { setErro('ID do cliente e arquivo são obrigatórios.'); return; }
    setErro(''); setSucesso(''); setLoading(true); setStatus(null);

    const formData = new FormData();
    formData.append('arquivo', arquivo);
    if (cabecas)  formData.append('cabecas', cabecas);
    if (cpf)      formData.append('destinatario_cpf', cpf);

    try {
      const res = await uploadNfae(clientId, formData);
      const tid = res.data?.task_id || res.data?.taskId;
      if (tid) {
        setTaskId(tid);
      } else {
        setSucesso('Upload concluído com sucesso.');
        setLoading(false);
      }
    } catch (err) {
      const msg = err.response?.data?.detail || err.response?.data?.message || 'Falha no upload.';
      setErro(msg);
      setLoading(false);
    }
  };

  const progressPercent = status?.progresso ?? status?.progress ?? (loading && !taskId ? 0 : null);
  const statusLabel = {
    pendente: 'Aguardando processamento...',
    processando: 'Executando pipeline HORIZON-BLUE ONE...',
    concluido: 'Concluído',
    done: 'Concluído',
    erro: 'Erro',
    failed: 'Falha',
  }[status?.status] || (loading ? 'Enviando arquivo...' : '');

  const inputStyle = {
    width: '100%', padding: '0.75rem 1rem', background: 'rgba(0,196,255,0.04)',
    border: '1px solid rgba(0,196,255,0.2)', borderRadius: 4,
    color: '#e0f4ff', fontSize: '0.875rem', outline: 'none', boxSizing: 'border-box',
    fontFamily: 'IBM Plex Sans, sans-serif',
  };

  return (
    <div style={{ fontFamily: 'IBM Plex Sans, sans-serif', maxWidth: 640 }}>
      <h2 style={{ color: '#fff', marginBottom: '0.25rem', fontSize: '1.25rem' }}>Nova Auditoria NFA-e</h2>
      <p style={{ color: '#4a6b8a', fontSize: '0.75rem', marginBottom: '2rem', fontFamily: 'IBM Plex Mono, monospace' }}>
        Upload de PDF/XML · Pipeline RE-1 → XGBoost → F1-F6 → A-07 → A-08
      </p>

      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        {/* ID do cliente */}
        <div>
          <label style={{ display: 'block', fontSize: '0.65rem', color: '#4a6b8a', letterSpacing: '0.15em', marginBottom: '0.4rem', fontFamily: 'IBM Plex Mono, monospace' }}>
            ID DO CLIENTE *
          </label>
          <input type="text" value={clientId} onChange={e => setClientId(e.target.value)} placeholder="cliente-001" required style={inputStyle} />
        </div>

        {/* CPF do destinatário (anonimizado via @Delta) */}
        <div>
          <label style={{ display: 'block', fontSize: '0.65rem', color: '#4a6b8a', letterSpacing: '0.15em', marginBottom: '0.4rem', fontFamily: 'IBM Plex Mono, monospace' }}>
            CPF DO DESTINATÁRIO <span style={{ color: '#00c47a' }}>(@Delta — anonimizado antes do LLM)</span>
          </label>
          <input type="text" value={cpf} onChange={e => setCpf(e.target.value)} placeholder="000.000.000-00" style={inputStyle} />
        </div>

        {/* Cabeças de gado */}
        <div>
          <label style={{ display: 'block', fontSize: '0.65rem', color: '#4a6b8a', letterSpacing: '0.15em', marginBottom: '0.4rem', fontFamily: 'IBM Plex Mono, monospace' }}>
            CABEÇAS (bovino/suíno/frango)
          </label>
          <input type="number" value={cabecas} onChange={e => setCabecas(e.target.value)} placeholder="ex: 150" min="0" style={inputStyle} />
        </div>

        {/* Arquivo PDF/XML */}
        <div>
          <label style={{ display: 'block', fontSize: '0.65rem', color: '#4a6b8a', letterSpacing: '0.15em', marginBottom: '0.4rem', fontFamily: 'IBM Plex Mono, monospace' }}>
            ARQUIVO NFA-e (PDF ou XML) *
          </label>
          <div
            onClick={() => fileRef.current?.click()}
            style={{
              padding: '1.5rem', border: '1px dashed rgba(0,196,255,0.3)', borderRadius: 6,
              background: 'rgba(0,196,255,0.03)', cursor: 'pointer', textAlign: 'center',
              color: '#4a6b8a', fontSize: '0.8rem',
            }}
          >
            {arquivo ? (
              <span style={{ color: '#00c4ff' }}>{arquivo.name} ({(arquivo.size / 1024).toFixed(1)} KB)</span>
            ) : (
              <span>Clique para selecionar PDF ou XML da NFA-e</span>
            )}
          </div>
          <input
            ref={fileRef} type="file" accept=".pdf,.xml" style={{ display: 'none' }}
            onChange={e => setArquivo(e.target.files[0] || null)}
          />
        </div>

        {/* Progresso */}
        {loading && (
          <div>
            <div style={{ fontSize: '0.7rem', color: '#7bafc4', fontFamily: 'IBM Plex Mono, monospace', marginBottom: '0.4rem' }}>
              {statusLabel}
            </div>
            <div style={{ height: 4, background: 'rgba(0,196,255,0.1)', borderRadius: 2, overflow: 'hidden' }}>
              <div style={{
                height: '100%', background: '#00c4ff', borderRadius: 2,
                width: progressPercent != null ? `${progressPercent}%` : '100%',
                animation: progressPercent == null ? 'progress-indeterminate 1.5s infinite' : 'none',
                transition: 'width 0.5s ease',
              }} />
            </div>
          </div>
        )}

        {/* Mensagens */}
        {erro && <div style={{ padding: '0.75rem', background: 'rgba(255,71,87,0.1)', border: '1px solid rgba(255,71,87,0.3)', borderRadius: 4, color: '#ff6b7a', fontSize: '0.8rem' }}>{erro}</div>}
        {sucesso && <div style={{ padding: '0.75rem', background: 'rgba(0,196,127,0.1)', border: '1px solid rgba(0,196,127,0.3)', borderRadius: 4, color: '#00c47a', fontSize: '0.8rem' }}>{sucesso}</div>}

        <button
          type="submit" disabled={loading}
          style={{
            marginTop: '0.5rem', padding: '0.875rem', background: loading ? 'rgba(0,196,255,0.03)' : 'rgba(0,196,255,0.1)',
            border: '1px solid rgba(0,196,255,0.4)', borderRadius: 4,
            color: '#00c4ff', fontSize: '0.8rem', letterSpacing: '0.2em',
            fontFamily: 'IBM Plex Mono, monospace', cursor: loading ? 'not-allowed' : 'pointer',
          }}
        >
          {loading ? 'PROCESSANDO...' : 'ENVIAR PARA AUDITORIA →'}
        </button>
      </form>

      <style>{`
        @keyframes progress-indeterminate {
          0% { transform: translateX(-100%); width: 60% }
          100% { transform: translateX(200%); width: 60% }
        }
      `}</style>
    </div>
  );
};

export default UploadNFA;
