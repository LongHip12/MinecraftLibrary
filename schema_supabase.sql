-- Paste toàn bộ đoạn này vào SQL Editor của Supabase Dashboard
  -- (SQL Editor → New query → Paste → Run)

  CREATE TABLE IF NOT EXISTS backups (
      id          UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
      label       TEXT        NOT NULL DEFAULT 'Manual',
      data        JSONB       NOT NULL,
      created_at  TIMESTAMPTZ DEFAULT NOW()
  );

  -- Tự động xóa backup cũ, chỉ giữ 50 bản gần nhất
  CREATE OR REPLACE FUNCTION cleanup_old_backups()
  RETURNS TRIGGER LANGUAGE plpgsql AS $$
  BEGIN
      DELETE FROM backups
      WHERE id IN (
          SELECT id FROM backups
          ORDER BY created_at DESC
          OFFSET 50
      );
      RETURN NEW;
  END;
  $$;

  DROP TRIGGER IF EXISTS limit_backups ON backups;
  CREATE TRIGGER limit_backups
      AFTER INSERT ON backups
      FOR EACH ROW EXECUTE FUNCTION cleanup_old_backups();

  -- Cấp quyền truy cập cho các role của Supabase/PostgREST
  GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
  GRANT ALL ON TABLE public.backups TO anon, authenticated, service_role;
  GRANT EXECUTE ON FUNCTION cleanup_old_backups() TO anon, authenticated, service_role;

  -- Bật RLS và thêm policy cho phép service_role toàn quyền
  ALTER TABLE public.backups ENABLE ROW LEVEL SECURITY;

  DROP POLICY IF EXISTS "service_role_all" ON public.backups;
  CREATE POLICY "service_role_all" ON public.backups
      FOR ALL
      TO service_role
      USING (true)
      WITH CHECK (true);
  