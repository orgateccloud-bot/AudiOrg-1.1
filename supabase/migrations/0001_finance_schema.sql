-- ============================================================================
-- OrgAudi — Schema Financeiro inicial (Supabase / Orgatec-data)
-- ----------------------------------------------------------------------------
-- Cria as 4 tabelas usadas por nfa_extractor/infrastructure/supabase/* :
--   profiles, categories, transactions, predictions
--
-- Inclui:
--   - Extensões necessárias (uuid-ossp)
--   - Foreign keys para auth.users
--   - Triggers de updated_at
--   - Row Level Security (RLS) por user_id
--   - Índices de performance
--
-- Como aplicar:
--   1. Supabase Studio → SQL Editor → cole este arquivo → Run
--   OU
--   2. supabase db push (com Supabase CLI configurada)
-- ============================================================================

-- Extensões -------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Helper: trigger genérico de updated_at -------------------------------------
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

-- ============================================================================
-- 1) profiles — extensão de auth.users (1:1)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.profiles (
    id            UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    display_name  TEXT,
    avatar_url    TEXT,
    currency      TEXT NOT NULL DEFAULT 'BRL',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS trg_profiles_updated_at ON public.profiles;
CREATE TRIGGER trg_profiles_updated_at
    BEFORE UPDATE ON public.profiles
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "profiles_select_own" ON public.profiles;
CREATE POLICY "profiles_select_own" ON public.profiles
    FOR SELECT USING (auth.uid() = id);

DROP POLICY IF EXISTS "profiles_insert_own" ON public.profiles;
CREATE POLICY "profiles_insert_own" ON public.profiles
    FOR INSERT WITH CHECK (auth.uid() = id);

DROP POLICY IF EXISTS "profiles_update_own" ON public.profiles;
CREATE POLICY "profiles_update_own" ON public.profiles
    FOR UPDATE USING (auth.uid() = id);

-- Auto-cria profile quando um auth.users é inserido
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    INSERT INTO public.profiles (id, display_name)
    VALUES (NEW.id, NEW.raw_user_meta_data->>'display_name')
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- ============================================================================
-- 2) categories — categorias de receita/despesa por usuário
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.categories (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    type        TEXT NOT NULL CHECK (type IN ('income', 'expense')),
    icon        TEXT,
    color       TEXT,
    is_default  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, name, type)
);

CREATE INDEX IF NOT EXISTS idx_categories_user_id ON public.categories(user_id);
CREATE INDEX IF NOT EXISTS idx_categories_type    ON public.categories(type);

DROP TRIGGER IF EXISTS trg_categories_updated_at ON public.categories;
CREATE TRIGGER trg_categories_updated_at
    BEFORE UPDATE ON public.categories
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.categories ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "categories_all_own" ON public.categories;
CREATE POLICY "categories_all_own" ON public.categories
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- ============================================================================
-- 3) transactions — receitas e despesas
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.transactions (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id           UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    category_id       UUID REFERENCES public.categories(id) ON DELETE SET NULL,
    type              TEXT NOT NULL CHECK (type IN ('income', 'expense')),
    amount            NUMERIC(14, 2) NOT NULL CHECK (amount > 0),
    description       TEXT,
    transaction_date  DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_transactions_user_id          ON public.transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_transactions_user_date        ON public.transactions(user_id, transaction_date DESC);
CREATE INDEX IF NOT EXISTS idx_transactions_user_category    ON public.transactions(user_id, category_id);
CREATE INDEX IF NOT EXISTS idx_transactions_user_type_date   ON public.transactions(user_id, type, transaction_date DESC);

DROP TRIGGER IF EXISTS trg_transactions_updated_at ON public.transactions;
CREATE TRIGGER trg_transactions_updated_at
    BEFORE UPDATE ON public.transactions
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.transactions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "transactions_all_own" ON public.transactions;
CREATE POLICY "transactions_all_own" ON public.transactions
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- ============================================================================
-- 4) predictions — saídas de modelos preditivos
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.predictions (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id           UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    prediction_type   TEXT NOT NULL CHECK (prediction_type IN ('cashflow', 'expense_trend', 'income_trend', 'anomaly')),
    period_start      DATE NOT NULL,
    period_end        DATE NOT NULL,
    predicted_amount  NUMERIC(14, 2) NOT NULL,
    confidence_score  NUMERIC(4, 3) NOT NULL CHECK (confidence_score >= 0 AND confidence_score <= 1),
    model_version     TEXT NOT NULL,
    metadata          JSONB,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (period_end >= period_start)
);

CREATE INDEX IF NOT EXISTS idx_predictions_user_id        ON public.predictions(user_id);
CREATE INDEX IF NOT EXISTS idx_predictions_user_type_date ON public.predictions(user_id, prediction_type, period_start DESC);

DROP TRIGGER IF EXISTS trg_predictions_updated_at ON public.predictions;
CREATE TRIGGER trg_predictions_updated_at
    BEFORE UPDATE ON public.predictions
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.predictions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "predictions_all_own" ON public.predictions;
CREATE POLICY "predictions_all_own" ON public.predictions
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- ============================================================================
-- Permissões — service_role bypass RLS, anon/authenticated obedecem RLS
-- ============================================================================
GRANT USAGE ON SCHEMA public TO anon, authenticated;
GRANT ALL  ON ALL TABLES    IN SCHEMA public TO anon, authenticated;
GRANT ALL  ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated;
