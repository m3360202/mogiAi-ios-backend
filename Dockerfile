FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖（包括 OpenCV 和视频处理所需的库）
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    postgresql-client \
    # OpenCV 运行时依赖（更新了包名以兼容新版 Debian）
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    # 视频处理依赖（ffmpeg 及相关库）
    ffmpeg \
    libavcodec-dev \
    libavformat-dev \
    libavutil-dev \
    libswscale-dev \
    libswresample-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制项目配置文件和依赖文件
COPY pyproject.toml requirements.txt ./

# 先安装除了本地包之外的所有依赖（跳过 -e .）
RUN pip install --no-cache-dir --upgrade pip && \
    sed '/^-e \./d' requirements.txt > /tmp/requirements.txt && \
    pip install --no-cache-dir -r /tmp/requirements.txt

# 复制应用代码
COPY . .

# 安装本地包（-e . 需要代码已存在）
RUN pip install --no-cache-dir -e . || true

# 创建上传目录和日志目录
RUN mkdir -p /app/uploads /app/logs /app/temp_videos

# 设置 OpenCV 环境变量（无头模式，不需要显示设备）
ENV OPENCV_VIDEOIO_PRIORITY_MSMF=0
ENV QT_QPA_PLATFORM=offscreen

# 设置非 root 用户（安全最佳实践）
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# 暴露端口
EXPOSE 8000

# 启动命令 - 使用生产级别的配置
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--timeout-keep-alive", "300"]

