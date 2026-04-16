-- Create storage bucket for interview videos if not exists
INSERT INTO storage.buckets (id, name, public)
VALUES ('interview-videos', 'interview-videos', true)
ON CONFLICT (id) DO NOTHING;

-- 删除可能存在的旧策略
DROP POLICY IF EXISTS "Allow authenticated users to upload videos" ON storage.objects;
DROP POLICY IF EXISTS "Allow users to read their own videos" ON storage.objects;
DROP POLICY IF EXISTS "Allow users to delete their own videos" ON storage.objects;
DROP POLICY IF EXISTS "Allow public to read videos" ON storage.objects;
DROP POLICY IF EXISTS "Anyone can upload interview videos" ON storage.objects;
DROP POLICY IF EXISTS "Anyone can read interview videos" ON storage.objects;
DROP POLICY IF EXISTS "Authenticated users can delete interview videos" ON storage.objects;

-- Set up RLS policies for the interview-videos bucket
-- 允许认证用户上传视频到 interview-videos bucket
CREATE POLICY "Anyone can upload interview videos"
ON storage.objects
FOR INSERT
TO authenticated
WITH CHECK (bucket_id = 'interview-videos');

-- 允许所有人读取视频（因为 bucket 是 public）
CREATE POLICY "Anyone can read interview videos"
ON storage.objects
FOR SELECT
TO public
USING (bucket_id = 'interview-videos');

-- 允许认证用户删除自己的视频
CREATE POLICY "Authenticated users can delete interview videos"
ON storage.objects
FOR DELETE
TO authenticated
USING (bucket_id = 'interview-videos');

