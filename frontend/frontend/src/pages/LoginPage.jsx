import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Shield, Lock, Mail } from 'lucide-react';
import MatrixBackground from '../components/MatrixBackground';
import api from '../services/api';

const LoginPage = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState('');

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    setErro('');
    try {
      const params = new URLSearchParams();
      params.append('username', email);
      params.append('password', password);
      const res = await api.post('/auth/login', params, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      });
      localStorage.setItem('orgatec_token', res.data.access_token);
      localStorage.setItem('orgatec_refresh', res.data.refresh_token);
      window.location.href = '/dashboard';
    } catch (err) {
      const detalhe = err.response?.data?.detail || 'Credenciais inválidas.';
      setErro(detalhe);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-sovereign-950 relative overflow-hidden">
      <MatrixBackground />
      
      <motion.div 
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="max-w-md w-full relative z-10"
      >
        <div className="text-center mb-6">
          {/* Imagem Estratégica Reduzida (Diretriz do Usuário) */}
          <motion.div
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className="mb-4 overflow-hidden rounded-xl border border-sovereign-800 shadow-2xl max-w-[240px] mx-auto"
          >
            <img 
              src="/orgatecIA.jpg" 
              alt="ORGATEC AI" 
              className="w-full h-auto object-cover grayscale hover:grayscale-0 transition-all duration-700"
            />
          </motion.div>

          <div className="flex justify-center items-center gap-3 mb-1">
            <Shield size={24} className="text-sovereign-cyan" />
            <h1 className="text-3xl font-black tracking-tighter">ORGATEC</h1>
          </div>
          <p className="text-sovereign-600 font-bold tracking-[0.2em] text-[10px]">SOVEREIGN AUDIT SYSTEM</p>
        </div>

        <div className="sovereign-card p-8 bg-sovereign-950/80 backdrop-blur-md">
          <form onSubmit={handleLogin} className="space-y-5">
            <div>
              <label className="block text-[10px] font-bold text-sovereign-500 mb-2 tracking-widest uppercase">E-mail Corporativo</label>
              <div className="relative">
                <Mail className="absolute left-3 top-3 text-sovereign-700" size={16} />
                <input 
                  type="text"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full bg-transparent border border-sovereign-800 rounded-lg py-2.5 pl-10 pr-4 text-white focus:border-sovereign-cyan transition-all outline-none text-sm"
                  placeholder="exemplo@orgatec.com.br"
                  required
                />
              </div>
            </div>

            <div>
              <label className="block text-[10px] font-bold text-sovereign-500 mb-2 tracking-widest uppercase">Senha</label>
              <div className="relative">
                <Lock className="absolute left-3 top-3 text-sovereign-700" size={16} />
                <input 
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full bg-transparent border border-sovereign-800 rounded-lg py-2.5 pl-10 pr-4 text-white focus:border-sovereign-cyan transition-all outline-none text-sm"
                  placeholder="••••••••"
                  required
                />
              </div>
            </div>

            {erro && (
              <p className="text-red-400 text-xs text-center font-bold">{erro}</p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-sovereign-cyan/20 hover:bg-sovereign-cyan border border-sovereign-cyan/40 text-sovereign-cyan hover:text-white font-black py-3 rounded-lg transition-all active:scale-[0.98] disabled:opacity-50 text-sm"
            >
              {loading ? 'AUTENTICANDO...' : 'ACESSAR PORTAL'}
            </button>
          </form>
        </div>
        
        <p className="text-center mt-8 text-[9px] text-sovereign-800 tracking-[0.4em] font-bold">
          ORGATEC SOVEREIGN SHIELD V6.3
        </p>
      </motion.div>
    </div>
  );
};

export default LoginPage;
