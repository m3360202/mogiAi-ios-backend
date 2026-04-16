-- 在 Supabase SQL Editor 中直接执行此脚本
-- 添加用户性格和就业倾向字段到 users 表

-- 添加性格字段（JSON 数组格式）
ALTER TABLE users 
ADD COLUMN IF NOT EXISTS personalities TEXT;

-- 添加就业倾向字段（JSON 数组格式）
ALTER TABLE users 
ADD COLUMN IF NOT EXISTS career_tendencies TEXT;

-- 添加注释（PostgreSQL 语法）
COMMENT ON COLUMN users.personalities IS '用户性格特征，JSON 数组格式存储';
COMMENT ON COLUMN users.career_tendencies IS '用户就业倾向，JSON 数组格式存储';

-- 验证字段是否添加成功
SELECT 
  column_name, 
  data_type, 
  is_nullable
FROM information_schema.columns
WHERE table_name = 'users' 
  AND column_name IN ('personalities', 'career_tendencies');

