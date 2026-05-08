import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Upload, FileText, Activity, CheckCircle, AlertTriangle,
  Loader2, Plus, Trash2, Download, X, ChevronDown,
  BarChart3, ShieldAlert, FileDown, Zap, AlertCircle,
} from 'lucide-react';
import api from '../services/api';

// ── Módulo principal ─────────────────────────────────────────────────────────

const AuditoriaModule = () => {
  const [tab, setTab] = useState('nfae'); // 'nfae' | 'upload'

  return (
    <div className="p-10 max-w-6xl">
      <div className="flex items-start justify-between mb-8">
        <div>
          <h1 className="text-3xl font-black tracking-tight text-white">Célula de Auditoria Forense</h1>
          <p className="text-sovereign-500 mt-1 text-sm">Motor ORGATEC HORIZON-BLUE ONE — Pipeline RE-1 → XGBoost → F1-F6 → A-07 → A-08</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-sovereign-900/50 border border-sovereign-800 rounded-xl p-1 mb-8 w-fit">
        <button
          onClick={() => setTab('nfae')}
          className={`px-5 py-2.5 rounded-lg text-sm font-bold transition-all
            ${tab === 'nfae' ? 'bg-sovereign-cyan text-white shadow-lg' : 'text-sovereign-500 hover:text-white'}`}
        >
          <span className="flex items-center gap-2"><Zap size={14} /> Auditoria NFA-e</span>
        </button>
        <button
          onClick={() => setTab('upload')}
          className={`px-5 py-2.5 rounded-lg text-sm font-bold transition-all
            ${tab === 'upload' ? 'bg-sovereign-cyan text-white shadow-lg' : 'text-sovereign-500 hover:text-white'}`}
        >
          <span className="flex items-center gap-2"><Upload size={14} /> Upload PDF (legado)</span>
        </button>
      </div>

      <AnimatePresence mode="wait">
        {tab === 'nfae' ? (
          <motion.div key="nfae" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <NFAeAuditoria />
          </motion.div>
        ) : (
          <motion.div key="upload" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <UploadLegado />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

// ── Pipeline NFA-e ────────────────────────────────────────────────────────────

const NATUREZAS = ['VENDA', 'COMPRA', 'TRÂNSITO', 'DEVOLUÇÃO'];
const POSICOES  = ['REMETENTE', 'DESTINATÁRIO'];
const ATIVIDADES = ['bovino', 'suino', 'avícola', 'caprino', 'ovino', 'equino', 'soja', 'milho', 'algodão', 'outro'];

const notaVazia = () => ({
  numero: '', data: new Date().toISOString().slice(0, 10),
  natureza: 'VENDA', valor_total: '',
  remetente_cpf: '', remetente_nome: '',
  destinatario_cpf: '', destinatario_nome: '',
  cfop: '5101', cabecas: '', municipio: '',
  posicao: 'DESTINATÁRIO', tipo_doc: 'nfa-e', atividade: 'bovino',
});

const NFAeAuditoria = () => {
  const [clientes, setClientes]   = useState([]);
  const [clienteId, setClienteId] = useState('');
  const [isPj, setIsPj]           = useState(false);
  const [isSegurado, setIsSegurado] = useState(true);
  const [notas, setNotas]         = useState([]);
  const [form, setForm]           = useState(notaVazia());
  const [showForm, setShowForm]   = useState(false);
  const [loading, setLoading]     = useState(false);
  const [resultado, setResultado] = useState(null);
  const [erro, setErro]           = useState('');

  useEffect(() => {
    api.get('/clientes/').then(r => setClientes(r.data)).catch(() => {});
  }, []);

  const clienteSelecionado = clientes.find(c => String(c.id) === String(clienteId));

  const adicionarNota = (e) => {
    e.preventDefault();
    if (!form.numero || !form.valor_total) return;
    setNotas(prev => [...prev, { ...form, valor_total: parseFloat(form.valor_total), cabecas: parseInt(form.cabecas) || 0 }]);
    setForm(notaVazia());
    setShowForm(false);
  };

  const removerNota = (idx) => setNotas(prev => prev.filter((_, i) => i !== idx));

  const executarAuditoria = async () => {
    if (!clienteSelecionado || notas.length === 0) return;
    setLoading(true);
    setErro('');
    setResultado(null);
    try {
      const payload = {
        contribuinte_cpf:  clienteSelecionado.cpf_cnpj,
        contribuinte_nome: clienteSelecionado.nome,
        is_pj:             isPj,
        is_segurado_especial: isSegurado,
        notas,
      };
      const res = await api.post('/auditoria/nfae', payload);
      setResultado(res.data);
    } catch (err) {
      setErro(err.response?.data?.detail || 'Erro ao executar auditoria');
    } finally {
      setLoading(false);
    }
  };

  const downloadJSON = () => {
    if (!resultado) return;
    const blob = new Blob([JSON.stringify(resultado, null, 2)], { type: 'application/json' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = `auditoria_${clienteSelecionado?.nome?.replace(/\s+/g, '_') || 'resultado'}_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const downloadPDF = async () => {
    if (!resultado?.result_id) return;
    try {
      const res = await api.get(`/auditoria/relatorio/${resultado.result_id}/pdf`, { responseType: 'blob' });
      const url = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      const a   = document.createElement('a');
      a.href    = url;
      a.download = `relatorio_nfae_${resultado.result_id.slice(0, 8)}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      alert('Erro ao gerar PDF');
    }
  };

  return (
    <div className="space-y-6">
      {/* Config */}
      <div className="sovereign-card p-6">
        <h3 className="text-xs font-bold text-sovereign-500 uppercase tracking-widest mb-4">Configuração da Auditoria</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          <div>
            <label className="block text-xs font-bold text-sovereign-500 uppercase tracking-widest mb-2">Contribuinte</label>
            <select
              value={clienteId}
              onChange={e => setClienteId(e.target.value)}
              className="w-full bg-sovereign-900 border border-sovereign-700 rounded-xl px-4 py-3 text-white outline-none focus:border-sovereign-cyan transition-all text-sm"
            >
              <option value="">— Selecione o cliente —</option>
              {clientes.map(c => (
                <option key={c.id} value={c.id}>{c.nome} ({c.cpf_cnpj})</option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-3 justify-center">
            <Toggle label="Pessoa Jurídica (PJ)" value={isPj} onChange={setIsPj} />
            <Toggle label="Segurado Especial" value={isSegurado} onChange={setIsSegurado} />
          </div>
          <div className="flex items-end">
            <button
              onClick={executarAuditoria}
              disabled={!clienteSelecionado || notas.length === 0 || loading}
              className="w-full flex items-center justify-center gap-2 bg-sovereign-cyan hover:bg-sovereign-neon text-white font-black py-3 rounded-xl transition-all disabled:opacity-40 disabled:cursor-not-allowed text-sm"
            >
              {loading ? <Loader2 size={18} className="animate-spin" /> : <Zap size={18} />}
              {loading ? 'Executando...' : 'Executar Auditoria'}
            </button>
          </div>
        </div>
      </div>

      {/* Notas */}
      <div className="sovereign-card p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xs font-bold text-sovereign-500 uppercase tracking-widest">
            Notas Fiscais Avulsas
            {notas.length > 0 && <span className="ml-2 bg-sovereign-cyan/20 text-sovereign-cyan px-2 py-0.5 rounded-full text-xs">{notas.length}</span>}
          </h3>
          <button
            onClick={() => setShowForm(s => !s)}
            className="flex items-center gap-2 text-sovereign-cyan hover:text-white border border-sovereign-cyan/30 hover:border-sovereign-cyan px-4 py-2 rounded-xl text-xs font-bold transition-all"
          >
            {showForm ? <X size={14} /> : <Plus size={14} />}
            {showForm ? 'Cancelar' : 'Adicionar NFA'}
          </button>
        </div>

        <AnimatePresence>
          {showForm && (
            <motion.form
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              onSubmit={adicionarNota}
              className="overflow-hidden"
            >
              <div className="border border-sovereign-700 rounded-xl p-5 mb-4 bg-sovereign-900/30">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                  <Field label="Número NFA" value={form.numero} onChange={v => setForm(p => ({...p, numero: v}))} required />
                  <Field label="Data" type="date" value={form.data} onChange={v => setForm(p => ({...p, data: v}))} required />
                  <SelectField label="Natureza" value={form.natureza} onChange={v => setForm(p => ({...p, natureza: v}))} options={NATUREZAS} />
                  <Field label="Valor Total (R$)" type="number" value={form.valor_total} onChange={v => setForm(p => ({...p, valor_total: v}))} required placeholder="0.00" />
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                  <Field label="CPF Remetente" value={form.remetente_cpf} onChange={v => setForm(p => ({...p, remetente_cpf: v}))} />
                  <Field label="Nome Remetente" value={form.remetente_nome} onChange={v => setForm(p => ({...p, remetente_nome: v}))} />
                  <Field label="CPF Destinatário" value={form.destinatario_cpf} onChange={v => setForm(p => ({...p, destinatario_cpf: v}))} />
                  <Field label="Nome Destinatário" value={form.destinatario_nome} onChange={v => setForm(p => ({...p, destinatario_nome: v}))} />
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <Field label="CFOP" value={form.cfop} onChange={v => setForm(p => ({...p, cfop: v}))} placeholder="5101" />
                  <Field label="Cabeças" type="number" value={form.cabecas} onChange={v => setForm(p => ({...p, cabecas: v}))} placeholder="0" />
                  <Field label="Município" value={form.municipio} onChange={v => setForm(p => ({...p, municipio: v}))} />
                  <SelectField label="Posição" value={form.posicao} onChange={v => setForm(p => ({...p, posicao: v}))} options={POSICOES} />
                </div>
                <div className="grid grid-cols-2 gap-4 mt-4">
                  <SelectField label="Atividade" value={form.atividade} onChange={v => setForm(p => ({...p, atividade: v}))} options={ATIVIDADES} />
                  <div className="flex items-end">
                    <button type="submit" className="w-full bg-sovereign-cyan text-white font-bold py-2.5 rounded-xl text-sm flex items-center justify-center gap-2 hover:bg-sovereign-neon transition-all">
                      <Plus size={16} /> Adicionar
                    </button>
                  </div>
                </div>
              </div>
            </motion.form>
          )}
        </AnimatePresence>

        {notas.length === 0 ? (
          <div className="border border-dashed border-sovereign-700 rounded-xl py-10 flex flex-col items-center text-sovereign-700">
            <FileText size={32} className="mb-2 opacity-40" />
            <p className="text-sm font-bold">Nenhuma nota adicionada</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-sovereign-800">
                  {['Número', 'Data', 'Natureza', 'Valor', 'Atividade', 'Posição', ''].map(h => (
                    <th key={h} className="text-left px-3 py-2 text-sovereign-600 font-bold uppercase tracking-wider">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {notas.map((n, i) => (
                  <tr key={i} className="border-b border-sovereign-800/40 hover:bg-sovereign-900/20">
                    <td className="px-3 py-2.5 font-mono text-sovereign-300">{n.numero}</td>
                    <td className="px-3 py-2.5 text-sovereign-400">{n.data}</td>
                    <td className="px-3 py-2.5">
                      <span className={`px-2 py-0.5 rounded-full font-bold text-[10px]
                        ${n.natureza === 'VENDA' ? 'bg-green-900/40 text-green-400 border border-green-700/30' :
                          n.natureza === 'COMPRA' ? 'bg-blue-900/40 text-blue-400 border border-blue-700/30' :
                          'bg-sovereign-800 text-sovereign-400 border border-sovereign-700'}`}>
                        {n.natureza}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 text-white font-bold">{parseFloat(n.valor_total).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}</td>
                    <td className="px-3 py-2.5 text-sovereign-400">{n.atividade}</td>
                    <td className="px-3 py-2.5 text-sovereign-400">{n.posicao}</td>
                    <td className="px-3 py-2.5">
                      <button onClick={() => removerNota(i)} className="p-1 text-sovereign-700 hover:text-red-400 transition-colors">
                        <X size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="bg-sovereign-900/30">
                  <td colSpan={3} className="px-3 py-2.5 text-sovereign-500 font-bold text-xs">{notas.length} nota(s)</td>
                  <td className="px-3 py-2.5 text-sovereign-cyan font-black text-xs">
                    {notas.reduce((s, n) => s + parseFloat(n.valor_total || 0), 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}
                  </td>
                  <td colSpan={3} />
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </div>

      {/* Erro */}
      {erro && (
        <div className="sovereign-card p-5 border-red-800 bg-red-900/20 flex items-center gap-3">
          <AlertCircle size={20} className="text-red-400 shrink-0" />
          <p className="text-red-300 text-sm">{erro}</p>
        </div>
      )}

      {/* Resultado */}
      <AnimatePresence>
        {resultado && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-5"
          >
            {/* Header resultado */}
            <div className="sovereign-card p-6">
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-lg font-black text-white">Resultado da Auditoria</h3>
                <div className="flex gap-3">
                  <button
                    onClick={downloadJSON}
                    className="flex items-center gap-2 text-sovereign-400 hover:text-white border border-sovereign-700 hover:border-sovereign-500 px-4 py-2 rounded-xl text-xs font-bold transition-all"
                  >
                    <Download size={14} /> JSON
                  </button>
                  <button
                    onClick={downloadPDF}
                    className="flex items-center gap-2 bg-sovereign-cyan/20 hover:bg-sovereign-cyan border border-sovereign-cyan/40 text-sovereign-cyan hover:text-white px-4 py-2 rounded-xl text-xs font-bold transition-all"
                  >
                    <FileDown size={14} /> Baixar PDF
                  </button>
                </div>
              </div>
              <p className="text-sovereign-500 text-xs">
                Contribuinte: <span className="text-white font-bold">{resultado.contribuinte?.nome}</span> |
                Regime: <span className="text-white">{resultado.contribuinte?.regime}</span> |
                Hash: <span className="font-mono text-sovereign-400">{resultado.audit_hash?.slice(0, 16)}…</span>
              </p>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              {/* Score */}
              <ScoreCard score={resultado.score_risco} reApplicada={resultado.notas_re1_aplicada} />

              {/* Resumo Fiscal */}
              <ResumoFiscalCard fiscal={resultado.resumo_fiscal} />
            </div>

            {/* Detectores + Análise */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              <DetectoresCard assurance={resultado.analise_assurance} />
              <AnaliseNFACard analise={resultado.analise_nfa} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

// ── Cards de Resultado ────────────────────────────────────────────────────────

const ScoreCard = ({ score, reApplicada }) => {
  if (!score) return null;
  const nivelColor = {
    CRÍTICO: { bg: 'from-red-900/40 to-transparent', border: 'border-red-700/40', text: 'text-red-400', badge: 'bg-red-900/60 text-red-300 border-red-700/40' },
    ALTO:    { bg: 'from-orange-900/40 to-transparent', border: 'border-orange-700/40', text: 'text-orange-400', badge: 'bg-orange-900/60 text-orange-300 border-orange-700/40' },
    MÉDIO:   { bg: 'from-yellow-900/30 to-transparent', border: 'border-yellow-700/30', text: 'text-yellow-400', badge: 'bg-yellow-900/60 text-yellow-300 border-yellow-700/30' },
    BAIXO:   { bg: 'from-green-900/30 to-transparent', border: 'border-green-700/30', text: 'text-green-400', badge: 'bg-green-900/60 text-green-300 border-green-700/30' },
  }[score.nivel] || { bg: '', border: 'border-sovereign-700', text: 'text-sovereign-400', badge: 'bg-sovereign-800 text-sovereign-400 border-sovereign-700' };

  return (
    <div className={`sovereign-card p-6 bg-gradient-to-br ${nivelColor.bg} border ${nivelColor.border}`}>
      <h3 className="text-xs font-bold text-sovereign-500 uppercase tracking-widest mb-4">Score de Risco Fiscal</h3>
      <div className="flex items-end gap-4 mb-4">
        <span className={`text-6xl font-black ${nivelColor.text}`}>{score.score}</span>
        <div className="mb-1">
          <span className={`px-3 py-1 rounded-full text-xs font-black border ${nivelColor.badge}`}>{score.nivel}</span>
          <p className="text-sovereign-600 text-xs mt-1">/{score.modo === 'heuristico' ? 'heurístico' : 'XGBoost'}</p>
        </div>
      </div>
      {/* Progress bar */}
      <div className="h-2 bg-sovereign-900 rounded-full overflow-hidden mb-4">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${score.score}%` }}
          transition={{ duration: 0.8, ease: 'easeOut' }}
          className={`h-full ${score.nivel === 'CRÍTICO' ? 'bg-red-500' : score.nivel === 'ALTO' ? 'bg-orange-500' : score.nivel === 'MÉDIO' ? 'bg-yellow-500' : 'bg-green-500'}`}
        />
      </div>
      <div className="grid grid-cols-2 gap-2 text-xs">
        {Object.entries(score.shap_values || {}).slice(0, 4).map(([k, v]) => (
          <div key={k} className="flex justify-between bg-sovereign-900/50 px-2 py-1 rounded-lg">
            <span className="text-sovereign-500 truncate">{k.replace(/_/g, ' ')}</span>
            <span className="text-sovereign-300 font-mono ml-2">{v.toFixed(1)}</span>
          </div>
        ))}
      </div>
      {reApplicada > 0 && (
        <div className="mt-3 text-xs text-sovereign-500">
          <span className="text-sovereign-cyan font-bold">{reApplicada}</span> nota(s) reclassificada(s) pela RE-1
        </div>
      )}
    </div>
  );
};

const ResumoFiscalCard = ({ fiscal }) => {
  if (!fiscal) return null;
  const fmt = v => parseFloat(v || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
  const rows = [
    ['F1 Receita Imediata',    fiscal.f1_receita_imediata],
    ['F2 Gado em Trânsito',    fiscal.f2_transito],
    ['F4 Receita Bruta',       fiscal.f4_receita_bruta],
    ['F6 Despesas Dedutíveis', fiscal.f6_despesa],
    ['F5 Resultado Rural',     fiscal.f5_resultado_rural],
  ];
  return (
    <div className="sovereign-card p-6">
      <h3 className="text-xs font-bold text-sovereign-500 uppercase tracking-widest mb-4">Apuração Fiscal OrgAudi v4</h3>
      <div className="space-y-2 mb-4">
        {rows.map(([label, val]) => (
          <div key={label} className="flex justify-between items-center py-1.5 border-b border-sovereign-800/40">
            <span className="text-xs text-sovereign-400">{label}</span>
            <span className={`text-sm font-bold font-mono ${parseFloat(val) < 0 ? 'text-red-400' : 'text-white'}`}>{fmt(val)}</span>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="bg-sovereign-900/50 p-3 rounded-xl">
          <p className="text-xs text-sovereign-500 mb-1">FUNRURAL</p>
          <p className="text-sovereign-cyan font-black">{fmt(fiscal.funrural)}</p>
          <p className="text-xs text-sovereign-600">{(parseFloat(fiscal.aliquota_funrural || 0) * 100).toFixed(2)}% alíquota</p>
        </div>
        <div className="bg-sovereign-900/50 p-3 rounded-xl">
          <p className="text-xs text-sovereign-500 mb-1">IRPF Estimado</p>
          <p className="text-orange-400 font-black">{fmt(fiscal.irpf_estimado)}</p>
          <p className="text-xs text-sovereign-600">{fiscal.total_notas} nota(s)</p>
        </div>
      </div>
    </div>
  );
};

const DetectoresCard = ({ assurance }) => {
  const padroes = Array.isArray(assurance?.padroes_detectados) ? assurance.padroes_detectados : [];
  const TODOS = ['CARROSSEL_FISCAL', 'SMURFING_RURAL', 'FORNECEDOR_FANTASMA', 'DEVOLUCAO_POSTERIOR', 'ANOMALIA_TEMPORAL'];

  return (
    <div className="sovereign-card p-6">
      <h3 className="text-xs font-bold text-sovereign-500 uppercase tracking-widest mb-4">Detectores Forenses (A-07)</h3>
      <div className="space-y-2 mb-4">
        {TODOS.map(d => {
          const ativo = padroes.includes(d);
          return (
            <div key={d} className={`flex items-center gap-3 px-3 py-2 rounded-xl border ${ativo ? 'bg-red-900/20 border-red-700/30' : 'bg-sovereign-900/20 border-sovereign-800/30'}`}>
              {ativo ? <AlertTriangle size={15} className="text-red-400 shrink-0" /> : <CheckCircle size={15} className="text-green-500 shrink-0" />}
              <span className={`text-xs font-bold ${ativo ? 'text-red-300' : 'text-sovereign-400'}`}>{d.replace(/_/g, ' ')}</span>
              <span className={`ml-auto text-[10px] font-black px-2 py-0.5 rounded-full ${ativo ? 'bg-red-900/60 text-red-300 border border-red-700/40' : 'bg-green-900/30 text-green-400 border border-green-700/30'}`}>
                {ativo ? 'ALERTA' : 'OK'}
              </span>
            </div>
          );
        })}
      </div>
      {assurance?.recomendacao && (
        <div className="bg-sovereign-900/40 px-4 py-3 rounded-xl">
          <p className="text-xs text-sovereign-500 mb-0.5">Recomendação A-07</p>
          <p className="text-sm font-bold text-white">{assurance.recomendacao}</p>
          {assurance.criticidade && <p className="text-xs text-sovereign-400 mt-1">Criticidade: {assurance.criticidade}</p>}
        </div>
      )}
    </div>
  );
};

const AnaliseNFACard = ({ analise }) => (
  <div className="sovereign-card p-6">
    <h3 className="text-xs font-bold text-sovereign-500 uppercase tracking-widest mb-4">Análise Qualitativa (A-08)</h3>
    {!analise ? (
      <p className="text-sovereign-600 text-sm">Sem dados de análise</p>
    ) : analise.erro_claude ? (
      <div className="bg-orange-900/20 border border-orange-700/30 rounded-xl p-4">
        <div className="flex items-center gap-2 mb-2">
          <AlertTriangle size={16} className="text-orange-400" />
          <span className="text-orange-300 font-bold text-xs">Claude indisponível</span>
        </div>
        <p className="text-sovereign-400 text-xs">{analise.erro_claude}</p>
        {analise.alertas?.map((a, i) => <p key={i} className="text-sovereign-500 text-xs mt-1">• {a}</p>)}
      </div>
    ) : (
      <div className="space-y-4">
        {analise.probabilidade_autuacao != null && (
          <div className="bg-sovereign-900/40 p-4 rounded-xl">
            <p className="text-xs text-sovereign-500 mb-1">Probabilidade de Autuação</p>
            <div className="flex items-center gap-3">
              <div className="flex-1 h-2 bg-sovereign-800 rounded-full overflow-hidden">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${analise.probabilidade_autuacao * 100}%` }}
                  className={`h-full ${analise.probabilidade_autuacao > 0.6 ? 'bg-red-500' : analise.probabilidade_autuacao > 0.3 ? 'bg-yellow-500' : 'bg-green-500'}`}
                />
              </div>
              <span className="text-white font-black text-sm">{(analise.probabilidade_autuacao * 100).toFixed(0)}%</span>
            </div>
          </div>
        )}
        {analise.recomendacao_geral && (
          <div>
            <p className="text-xs text-sovereign-500 mb-1">Recomendação Geral</p>
            <p className="text-sm text-sovereign-300 leading-relaxed">{analise.recomendacao_geral}</p>
          </div>
        )}
        {analise.proximos_passos?.length > 0 && (
          <div>
            <p className="text-xs text-sovereign-500 mb-2">Próximos Passos</p>
            <ul className="space-y-1">
              {analise.proximos_passos.map((p, i) => (
                <li key={i} className="flex items-start gap-2 text-xs text-sovereign-400">
                  <span className="text-sovereign-cyan mt-0.5 shrink-0">›</span> {p}
                </li>
              ))}
            </ul>
          </div>
        )}
        {analise.alertas?.length > 0 && (
          <div className="space-y-1">
            {analise.alertas.map((a, i) => (
              <div key={i} className="flex items-center gap-2 text-xs text-orange-300 bg-orange-900/20 px-3 py-1.5 rounded-lg">
                <AlertTriangle size={12} className="shrink-0" /> {a}
              </div>
            ))}
          </div>
        )}
      </div>
    )}
  </div>
);

// ── Upload Legado (PDF) ───────────────────────────────────────────────────────

const UploadLegado = () => {
  const [files, setFiles]           = useState([]);
  const [taskId, setTaskId]         = useState(null);
  const [status, setStatus]         = useState(null);
  const [progressData, setProgressData] = useState({ progress: 0, status_text: '' });

  useEffect(() => {
    let interval;
    if (taskId && status === 'processing') {
      interval = setInterval(async () => {
        try {
          const res  = await api.get(`/auditoria/status/${taskId}`);
          const data = res.data;
          setProgressData({ progress: data.progress, status_text: data.status.replace('_', ' ').toUpperCase() });
          if (data.status === 'concluido') { setStatus('completed'); clearInterval(interval); }
          else if (data.status === 'erro') { setStatus('error'); clearInterval(interval); }
        } catch {}
      }, 2000);
    }
    return () => clearInterval(interval);
  }, [taskId, status]);

  const handleUpload = async () => {
    if (!files.length) return;
    setStatus('processing');
    const formData = new FormData();
    files.forEach(f => formData.append('files', f));
    try {
      const res = await api.post('/auditoria/upload/1', formData, { headers: { 'Content-Type': 'multipart/form-data' } });
      setTaskId(res.data.task_id);
    } catch { setStatus('error'); }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div className="lg:col-span-1 space-y-4">
        <label className="sovereign-card p-6 border-dashed border-2 border-sovereign-700 hover:border-sovereign-cyan transition-all cursor-pointer flex flex-col items-center py-12">
          <Upload className="text-sovereign-500 mb-3" size={36} />
          <span className="text-sm font-bold text-sovereign-400">Arraste ou selecione NFAs (PDF)</span>
          <input type="file" multiple accept=".pdf,.xml" className="hidden" onChange={e => setFiles(Array.from(e.target.files))} />
        </label>
        {files.length > 0 && (
          <div className="sovereign-card p-4 space-y-2">
            <p className="text-xs font-bold text-sovereign-600 uppercase">Lote</p>
            {files.map((f, i) => (
              <div key={i} className="flex items-center gap-2 text-xs text-sovereign-300">
                <FileText size={14} className="text-sovereign-cyan" /> {f.name}
              </div>
            ))}
            <button onClick={handleUpload} disabled={status === 'processing'} className="w-full mt-3 bg-sovereign-cyan text-white font-bold py-2.5 rounded-xl text-sm disabled:opacity-50 transition-all">
              DISPARAR AUDITORIA
            </button>
          </div>
        )}
      </div>
      <div className="lg:col-span-2">
        <AnimatePresence mode="wait">
          {status === 'processing' ? (
            <motion.div key="p" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="sovereign-card p-10 flex flex-col items-center justify-center text-center">
              <Loader2 size={48} className="text-sovereign-cyan animate-spin mb-4" />
              <h2 className="text-xl font-bold mb-2">Protocolo em Execução</h2>
              <p className="text-sovereign-400 mb-6 text-sm">{progressData.status_text}</p>
              <div className="w-full max-w-sm bg-sovereign-950 rounded-full h-2 overflow-hidden border border-sovereign-800">
                <motion.div animate={{ width: `${progressData.progress}%` }} className="h-full bg-sovereign-cyan" />
              </div>
              <span className="text-sovereign-cyan font-black mt-3">{progressData.progress}%</span>
            </motion.div>
          ) : status === 'completed' ? (
            <motion.div key="c" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="sovereign-card p-8">
              <div className="flex items-center gap-4 mb-6">
                <CheckCircle size={40} className="text-green-400" />
                <div>
                  <h2 className="text-xl font-bold">Veredito Concluído</h2>
                  <p className="text-sovereign-400 text-sm">Análise finalizada com sucesso.</p>
                </div>
              </div>
              <button className="bg-white text-sovereign-950 font-black px-6 py-3 rounded-xl hover:bg-slate-200 transition-all text-sm flex items-center gap-2">
                <FileDown size={16} /> BAIXAR LAUDO PDF
              </button>
            </motion.div>
          ) : (
            <div className="sovereign-card p-10 flex flex-col items-center justify-center text-center text-sovereign-700 border-dashed">
              <Activity size={48} className="mb-3 opacity-20" />
              <p className="text-sm">Aguardando submissão do lote PDF para iniciar protocolos.</p>
            </div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
};

// ── Componentes de formulário ────────────────────────────────────────────────

const Field = ({ label, value, onChange, type = 'text', required, placeholder }) => (
  <div>
    <label className="block text-[10px] font-bold text-sovereign-600 uppercase tracking-widest mb-1">{label}</label>
    <input
      type={type}
      value={value}
      onChange={e => onChange(e.target.value)}
      required={required}
      placeholder={placeholder}
      className="w-full bg-sovereign-900 border border-sovereign-700 rounded-lg px-3 py-2 text-white outline-none focus:border-sovereign-cyan transition-all text-xs"
    />
  </div>
);

const SelectField = ({ label, value, onChange, options }) => (
  <div>
    <label className="block text-[10px] font-bold text-sovereign-600 uppercase tracking-widest mb-1">{label}</label>
    <select
      value={value}
      onChange={e => onChange(e.target.value)}
      className="w-full bg-sovereign-900 border border-sovereign-700 rounded-lg px-3 py-2 text-white outline-none focus:border-sovereign-cyan transition-all text-xs"
    >
      {options.map(o => <option key={o} value={o}>{o}</option>)}
    </select>
  </div>
);

const Toggle = ({ label, value, onChange }) => (
  <button
    type="button"
    onClick={() => onChange(!value)}
    className={`flex items-center gap-2 text-xs font-bold transition-colors ${value ? 'text-sovereign-cyan' : 'text-sovereign-600'}`}
  >
    <div className={`w-9 h-5 rounded-full transition-all relative ${value ? 'bg-sovereign-cyan' : 'bg-sovereign-800'}`}>
      <div className={`w-3.5 h-3.5 bg-white rounded-full absolute top-0.5 transition-all ${value ? 'left-4.5' : 'left-0.5'}`} />
    </div>
    {label}
  </button>
);

export default AuditoriaModule;
