import axios from 'axios';

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8082';

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

// Interceptor: injeta JWT em todas as requisições
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('orgatec_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Interceptor: trata 401 global → redireciona para login
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('orgatec_token');
      window.location.href = '/login';
    }
    return Promise.reject(err);
  }
);

// ── Auth ─────────────────────────────────────────────────────────────────────
export const login = (email, senha) =>
  api.post('/auth/login', { email, senha });

// ── Health check ──────────────────────────────────────────────────────────────
export const ping = () => api.get('/ping');

// ── Stats / KPIs globais do sistema ──────────────────────────────────────────
export const getStats = () => api.get('/stats');

// ── Pipeline NFA-e (auditoria completa) ──────────────────────────────────────
export const runNfae = (payload) => api.post('/nfae', payload);

// ── Resultado de auditoria por ID ─────────────────────────────────────────────
export const getResultado = (id) => api.get(`/resultado/${id}`);

// ── Download de relatório PDF ─────────────────────────────────────────────────
export const getRelatorioPdf = async (id) => {
  const res = await api.get(`/relatorio/${id}/pdf`, { responseType: 'blob' });
  const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = `laudo-${id}.pdf`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.URL.revokeObjectURL(url);
};

// ── Upload de PDFs NFA-e (multipart) ─────────────────────────────────────────
export const uploadNfae = (clientId, formData) =>
  api.post(`/upload/${clientId}`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });

// ── Status de task assíncrona (polling) ──────────────────────────────────────
export const getTaskStatus = (taskId) => api.get(`/status/${taskId}`);

export default api;
