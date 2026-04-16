-- 添加用户性格和就业倾向字段
-- 运行命令: psql -U your_user -d your_database -f migrations/add_personalities_career_tendencies.sql

-- 添加性格字段（JSON 数组格式）
ALTER TABLE users 
ADD COLUMN IF NOT EXISTS personalities TEXT;

-- 添加就业倾向字段（JSON 数组格式）
ALTER TABLE users 
ADD COLUMN IF NOT EXISTS career_tendencies TEXT;

-- 添加注释
COMMENT ON COLUMN users.personalities IS '用户性格特征，JSON 数组格式存储';
COMMENT ON COLUMN users.career_tendencies IS '用户就业倾向，JSON 数组格式存储';

