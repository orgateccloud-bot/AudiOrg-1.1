import React, { useState, useEffect, useRef } from 'react';
import { Routes, Route, Link, useLocation, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard, Users, Search, Brain, LogOut, Shield,
  Send, Loader2, Plus, Trash2, TrendingUp, FileText,
  AlertTriangle, CheckCircle, X, ChevronRight, Activity,
  BarChart3, UserCheck, Zap,
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import AuditoriaModule from './AuditoriaModule';
import MatrixBackground from '../components/MatrixBackground';
import api from '../services/api';

// ── Layout Principal ─────────────────────────────────────────────────────────

const Dashboard = () => {
  const navigate  = useNavigate();
  const location  = useLocation();

  const handleLogout = () => {
    localStorage.removeItem('orgatec_token');
    window.location.href = '/login';
  };

  const navItems = [
    { icon: <LayoutDashboard size={18} />, label: 'Comando',   to: '/dashboard' },
    { icon: <Users size={18} />,           label: 'Clientes',  to: '/dashboard/clientes' },
    { icon: <Search size={18} />,          label: 'Auditoria', to: '/dashboard/auditoria' },
    { icon: <Brain size={18} />,           label: 'Agente',    to: '/dashboard/agente' },
  ];

  return (
    <div className="flex h-screen overflow-hidden bg-sovereign-950 relative">
      <MatrixBackground />

      {/* Sidebar */}
      <aside className="w-64 bg-sovereign-950/90 backdrop-blur-md border-r border-sovereign-800 flex flex-col p-6 z-20 shrink-0">
        <div className="flex items-center gap-3 mb-10">
          <div className="w-8 h-8 rounded-lg bg-sovereign-cyan/20 border border-sovereign-cyan/40 flex items-center justify-center">
            <Shield className="text-sovereign-cyan" size={16} />
          </div>
          <div>
            <h2 className="text-sm font-black tracking-widest text-white">ORGATEC</h2>
            <p className="text-[9px] text-sovereign-600 tracking-[0.3em] font-bold">SOVEREIGN v6.4</p>
          </div>
        </div>

        <nav className="flex-1 space-y-1">
          {navItems.map(item => {
            const active = location.pathname === item.to ||
              (item.to !== '/dashboard' && location.pathname.startsWith(item.to));
            return (
              <Link
                key={item.to}
                to={item.to}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all text-sm font-bold
                  ${active
                    ? 'bg-sovereign-cyan/15 text-sovereign-cyan border border-sovereign-cyan/20'
                    : 'text-sovereign-500 hover:bg-sovereign-900 hover:text-sovereign-300'}`}
              >
                {item.icon}
                <span>{item.label}</span>
                {active && <ChevronRight size={14} className="ml-auto" />}
              </Link>
            );
          })}
        </nav>

        <button
          onClick={handleLogout}
          className="flex items-center gap-3 text-sovereign-700 hover:text-red-400 transition-colors px-3 py-2.5 mt-auto rounded-xl hover:bg-red-900/10"
        >
          <LogOut size={18} />
          <span className="font-bold text-xs uppercase tracking-widest">Sair</span>
        </button>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto z-10">
        <Routes>
          <Route path="/"          element={<HomeModule />} />
          <Route path="/clientes"  element={<ClientesModule />} />
          <Route path="/auditoria" element={<AuditoriaModule />} />
          <Route path="/agente"    element={<AgenteModule />} />
        </Routes>
      </main>
    </div>
  );
};

// ── Componentes utilitários ──────────────────────────────────────────────────

const PageHeader = ({ title, subtitle, action }) => (
  <div className="flex items-start justify-between mb-8">
    <div>
      <h1 className="text-3xl font-black tracking-tight text-white">{title}</h1>
      {subtitle && <p className="text-sovereign-500 mt-1 text-sm">{subtitle}</p>}
    </div>
    {action}
  </div>
);

const StatCard = ({ icon, label, value, sub, color = 'cyan' }) => {
  const colors = {
    cyan:   'from-sovereign-cyan/10 to-transparent border-sovereign-cyan/20 text-sovereign-cyan',
    green:  'from-green-500/10  to-transparent border-green-500/20  text-green-400',
    orange: 'from-orange-500/10 to-transparent border-orange-500/20 text-orange-400',
    purple: 'from-purple-500/10 to-transparent border-purple-500/20 text-purple-400',
  };
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      className={`sovereign-card p-6 bg-gradient-to-br ${colors[color]}`}
    >
      <div className="flex items-center justify-between mb-4">
        <div className={`p-2 rounded-lg bg-current/10 ${colors[color].split(' ').pop()}`}>{icon}</div>
        <span className="text-xs text-sovereign-600 font-bold uppercase tracking-widest">{label}</span>
      </div>
      <p className="text-3xl font-black text-white">{value ?? '—'}</p>
      {sub && <p className="text-xs text-sovereign-500 mt-1">{sub}</p>}
    </motion.div>
  );
};

const Modal = ({ open, title, onClose, children }) => (
  <AnimatePresence>
    {open && (
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-6"
        onClick={onClose}
      >
        <motion.div
          initial={{ scale: 0.92, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.92, opacity: 0 }}
          onClick={e => e.stopPropagation()}
          className="sovereign-card w-full max-w-md p-8"
        >
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-xl font-black">{title}</h2>
            <button onClick={onClose} className="text-sovereign-600 hover:text-white transition-colors">
              <X size={20} />
            </button>
          </div>
          {children}
        </motion.div>
      </motion.div>
    )}
  </AnimatePresence>
);

// ── Home / Comando ───────────────────────────────────────────────────────────

const HomeModule = () => {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get('/stats')
      .then(r => setStats(r.data))
      .catch(() => setStats({ total_clientes: 0, total_laudos: 0, total_auditorias_nfae: 0, total_notas_processadas: 0, score_medio: 0 }))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="p-10 max-w-6xl">
      <PageHeader
        title="Centro de Comando"
        subtitle="Monitoramento em tempo real do sistema ORGATEC Sovereign Audit"
      />

      {loading ? (
        <div className="flex items-center gap-3 text-sovereign-500">
          <Loader2 size={20} className="animate-spin" />
          <span className="text-sm">Carregando telemetria...</span>
        </div>
      ) : (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-5 mb-10">
          <StatCard
            icon={<Users size={20} />}
            label="Clientes"
            value={stats?.total_clientes}
            sub="cadastrados na malha"
            color="cyan"
          />
          <StatCard
            icon={<FileText size={20} />}
            label="Auditorias PDF"
            value={stats?.total_laudos}
            sub="laudos gerados"
            color="purple"
          />
          <StatCard
            icon={<Zap size={20} />}
            label="NFA-e Analisadas"
            value={stats?.total_auditorias_nfae}
            sub={`${stats?.total_notas_processadas} notas processadas`}
            color="orange"
          />
          <StatCard
            icon={<BarChart3 size={20} />}
            label="Score Médio"
            value={stats?.score_medio ? `${stats.score_medio}` : '—'}
            sub="risco fiscal médio (0–100)"
            color="green"
          />
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="sovereign-card p-7">
          <h3 className="text-xs font-bold text-sovereign-500 uppercase tracking-widest mb-5">Status do Sistema</h3>
          <div className="space-y-3">
            {[
              { label: 'Motor OrgAudi v4 (RE-1 + F1-F6)', ok: true },
              { label: 'XGBoost Scorer (heurístico)', ok: true },
              { label: 'Detectores Forenses (5/5)', ok: true },
              { label: 'Claude API (A-07 / A-08)', ok: false },
              { label: 'SQLite (banco local)', ok: true },
            ].map(({ label, ok }) => (
              <div key={label} className="flex items-center gap-3 text-sm">
                {ok
                  ? <CheckCircle size={16} className="text-green-400 shrink-0" />
                  : <AlertTriangle size={16} className="text-orange-400 shrink-0" />}
                <span className={ok ? 'text-sovereign-300' : 'text-sovereign-500'}>{label}</span>
                <span className={`ml-auto text-xs font-bold ${ok ? 'text-green-400' : 'text-orange-400'}`}>
                  {ok ? 'ATIVO' : 'DEGRADADO'}
                </span>
              </div>
            ))}
          </div>
        </div>

        <div className="sovereign-card p-7">
          <h3 className="text-xs font-bold text-sovereign-500 uppercase tracking-widest mb-5">Pipeline HORIZON-BLUE</h3>
          <div className="space-y-2">
            {[
              { step: 'RE-1', desc: 'Reclassificação VENDA → COMPRA rural', color: 'bg-sovereign-cyan' },
              { step: 'XGBoost', desc: 'Score 0–100 com 8 features SEFAZ-GO', color: 'bg-purple-500' },
              { step: 'F1-F6', desc: 'Apuração fiscal FUNRURAL 2026', color: 'bg-blue-500' },
              { step: 'A-07', desc: 'Detectores forenses determinísticos', color: 'bg-orange-500' },
              { step: 'A-08', desc: 'Análise qualitativa + @Delta', color: 'bg-green-500' },
            ].map(({ step, desc, color }, i) => (
              <div key={step} className="flex items-center gap-3">
                <div className={`w-6 h-6 ${color} rounded-md flex items-center justify-center text-[10px] font-black text-white shrink-0`}>{i + 1}</div>
                <div>
                  <span className="text-xs font-bold text-white">{step}</span>
                  <span className="text-xs text-sovereign-500 ml-2">{desc}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

// ── Clientes ─────────────────────────────────────────────────────────────────

const ClientesModule = () => {
  const [clientes, setClientes]   = useState([]);
  const [loading, setLoading]     = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [confirmId, setConfirmId] = useState(null);
  const [form, setForm]           = useState({ nome: '', cpf_cnpj: '' });
  const [saving, setSaving]       = useState(false);
  const [erro, setErro]           = useState('');

  const carregar = () => {
    setLoading(true);
    api.get('/clientes/')
      .then(r => setClientes(r.data))
      .finally(() => setLoading(false));
  };

  useEffect(() => { carregar(); }, []);

  const handleAdd = async (e) => {
    e.preventDefault();
    if (!form.nome.trim() || !form.cpf_cnpj.trim()) return;
    setSaving(true);
    setErro('');
    try {
      await api.post('/clientes/', form);
      setShowModal(false);
      setForm({ nome: '', cpf_cnpj: '' });
      carregar();
    } catch (err) {
      setErro(err.response?.data?.detail || 'Erro ao cadastrar cliente');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id) => {
    try {
      await api.delete(`/clientes/${id}`);
      setConfirmId(null);
      carregar();
    } catch {
      alert('Erro ao remover cliente');
    }
  };

  return (
    <div className="p-10 max-w-5xl">
      <PageHeader
        title="Gestão de Clientes"
        subtitle="Base de contribuintes cadastrados para auditoria fiscal"
        action={
          <button
            onClick={() => { setShowModal(true); setErro(''); }}
            className="flex items-center gap-2 bg-sovereign-cyan/20 hover:bg-sovereign-cyan border border-sovereign-cyan/40 text-sovereign-cyan hover:text-white font-bold px-5 py-2.5 rounded-xl transition-all text-sm"
          >
            <Plus size={16} />
            Novo Cliente
          </button>
        }
      />

      {loading ? (
        <div className="flex items-center gap-3 text-sovereign-500 py-12 justify-center">
          <Loader2 size={24} className="animate-spin" />
        </div>
      ) : clientes.length === 0 ? (
        <div className="sovereign-card p-16 flex flex-col items-center justify-center text-center">
          <UserCheck size={48} className="text-sovereign-700 mb-4" />
          <p className="text-sovereign-500 font-bold">Nenhum cliente cadastrado</p>
          <p className="text-sovereign-700 text-sm mt-1">Clique em "Novo Cliente" para iniciar</p>
        </div>
      ) : (
        <div className="sovereign-card overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-sovereign-800 bg-sovereign-900/50">
                <th className="text-left px-6 py-4 text-xs font-bold text-sovereign-500 uppercase tracking-widest">ID</th>
                <th className="text-left px-6 py-4 text-xs font-bold text-sovereign-500 uppercase tracking-widest">Nome</th>
                <th className="text-left px-6 py-4 text-xs font-bold text-sovereign-500 uppercase tracking-widest">CPF / CNPJ</th>
                <th className="text-left px-6 py-4 text-xs font-bold text-sovereign-500 uppercase tracking-widest">Cadastro</th>
                <th className="px-6 py-4"></th>
              </tr>
            </thead>
            <tbody>
              {clientes.map((c, i) => (
                <motion.tr
                  key={c.id}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.04 }}
                  className="border-b border-sovereign-800/50 hover:bg-sovereign-900/30 transition-colors"
                >
                  <td className="px-6 py-4 text-sovereign-600 font-mono">#{c.id}</td>
                  <td className="px-6 py-4 font-bold text-white">{c.nome}</td>
                  <td className="px-6 py-4 font-mono text-sovereign-400">{c.cpf_cnpj}</td>
                  <td className="px-6 py-4 text-sovereign-500">
                    {c.data_cadastro ? new Date(c.data_cadastro).toLocaleDateString('pt-BR') : '—'}
                  </td>
                  <td className="px-6 py-4 text-right">
                    <button
                      onClick={() => setConfirmId(c.id)}
                      className="p-2 text-sovereign-700 hover:text-red-400 hover:bg-red-900/20 rounded-lg transition-all"
                    >
                      <Trash2 size={16} />
                    </button>
                  </td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Modal Novo Cliente */}
      <Modal open={showModal} title="Novo Cliente" onClose={() => setShowModal(false)}>
        <form onSubmit={handleAdd} className="space-y-5">
          <div>
            <label className="block text-xs font-bold text-sovereign-500 uppercase tracking-widest mb-2">Nome / Razão Social</label>
            <input
              value={form.nome}
              onChange={e => setForm(p => ({ ...p, nome: e.target.value }))}
              placeholder="João da Silva"
              required
              className="w-full bg-sovereign-900 border border-sovereign-700 rounded-xl px-4 py-3 text-white outline-none focus:border-sovereign-cyan transition-all text-sm"
            />
          </div>
          <div>
            <label className="block text-xs font-bold text-sovereign-500 uppercase tracking-widest mb-2">CPF / CNPJ</label>
            <input
              value={form.cpf_cnpj}
              onChange={e => setForm(p => ({ ...p, cpf_cnpj: e.target.value }))}
              placeholder="000.000.000-00"
              required
              className="w-full bg-sovereign-900 border border-sovereign-700 rounded-xl px-4 py-3 text-white outline-none focus:border-sovereign-cyan transition-all text-sm font-mono"
            />
          </div>
          {erro && <p className="text-red-400 text-xs font-bold">{erro}</p>}
          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={() => setShowModal(false)}
              className="flex-1 border border-sovereign-700 text-sovereign-400 hover:text-white py-3 rounded-xl font-bold text-sm transition-all"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={saving}
              className="flex-1 bg-sovereign-cyan text-white py-3 rounded-xl font-bold text-sm transition-all disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {saving ? <Loader2 size={16} className="animate-spin" /> : <Plus size={16} />}
              {saving ? 'Salvando...' : 'Cadastrar'}
            </button>
          </div>
        </form>
      </Modal>

      {/* Modal Confirmar Exclusão */}
      <Modal open={!!confirmId} title="Confirmar Remoção" onClose={() => setConfirmId(null)}>
        <p className="text-sovereign-400 text-sm mb-6">
          Esta ação irá remover o cliente e todos os dados vinculados. Deseja continuar?
        </p>
        <div className="flex gap-3">
          <button
            onClick={() => setConfirmId(null)}
            className="flex-1 border border-sovereign-700 text-sovereign-400 hover:text-white py-3 rounded-xl font-bold text-sm transition-all"
          >
            Cancelar
          </button>
          <button
            onClick={() => handleDelete(confirmId)}
            className="flex-1 bg-red-600 hover:bg-red-500 text-white py-3 rounded-xl font-bold text-sm transition-all flex items-center justify-center gap-2"
          >
            <Trash2 size={16} />
            Remover
          </button>
        </div>
      </Modal>
    </div>
  );
};

// ── Agente Chat ──────────────────────────────────────────────────────────────

const AgenteModule = () => {
  const [messages, setMessages] = useState([
    { role: 'assistant', content: 'Protocolo ORGATEC iniciado. Como posso auxiliar na investigação fiscal?' }
  ]);
  const [input, setInput]   = useState('');
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = async () => {
    if (!input.trim() || loading) return;
    const userMsg = { role: 'user', content: input };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);
    try {
      const res = await api.post('/agente/chat', { pergunta: input });
      setMessages(prev => [...prev, { role: 'assistant', content: res.data.response }]);
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Erro de conexão com o Núcleo de Inteligência.' }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full p-10 max-w-4xl">
      <PageHeader
        title="Agente ORGATEC"
        subtitle="Consulte o núcleo de inteligência fiscal em linguagem natural"
      />
      <div className="flex-1 overflow-y-auto space-y-4 mb-6 pr-2">
        {messages.map((m, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div className={`px-5 py-3.5 rounded-2xl max-w-[80%] text-sm leading-relaxed
              ${m.role === 'user'
                ? 'bg-sovereign-cyan/20 border border-sovereign-cyan/30 text-white'
                : 'bg-sovereign-900/70 border border-sovereign-800 text-sovereign-300'}`}>
              {m.content}
            </div>
          </motion.div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-sovereign-900/70 border border-sovereign-800 px-5 py-4 rounded-2xl">
              <Loader2 size={16} className="animate-spin text-sovereign-cyan" />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <div className="relative">
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && !e.shiftKey && sendMessage()}
          placeholder="Digite sua consulta fiscal..."
          className="w-full bg-sovereign-900 border border-sovereign-800 rounded-2xl py-4 pl-6 pr-14 outline-none focus:border-sovereign-cyan transition-all text-sm"
        />
        <button
          onClick={sendMessage}
          disabled={loading || !input.trim()}
          className="absolute right-4 top-3.5 text-sovereign-cyan hover:text-white transition-colors disabled:opacity-40"
        >
          <Send size={22} />
        </button>
      </div>
    </div>
  );
};

export default Dashboard;
