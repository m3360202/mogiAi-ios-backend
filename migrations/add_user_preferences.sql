-- 添加用户偏好字段
-- 运行命令: psql -U your_user -d your_database -f migrations/add_user_preferences.sql

-- 添加偏好行业字段
ALTER TABLE users 
ADD COLUMN IF NOT EXISTS preferred_industries TEXT;

-- 添加偏好职位字段
ALTER TABLE users 
ADD COLUMN IF NOT EXISTS preferred_positions TEXT;

-- 添加工作状态字段  
ALTER TABLE users 
ADD COLUMN IF NOT EXISTS work_status VARCHAR(50);

-- 添加注释
COMMENT ON COLUMN users.preferred_industries IS '用户偏好的行业，逗号分隔';
COMMENT ON COLUMN users.preferred_positions IS '用户偏好的职位，逗号分隔';
COMMENT ON COLUMN users.work_status IS '用户当前工作状态: student, new-grad, employed, job-seeking, freelance, career-change';

