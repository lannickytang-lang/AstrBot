FROM python:3.12-slim
WORKDIR /AstrBot

# Tencent Cloud internal mirrors: apt/pypi throughput from the VPS is 10-50x
# faster than the official endpoints; harmless elsewhere (fallback to public
# mirror domains that also resolve outside Tencent Cloud).
RUN sed -i 's|deb.debian.org|mirrors.tencent.com|g' /etc/apt/sources.list.d/debian.sources \
    && sed -i 's|security.debian.org|mirrors.tencent.com|g' /etc/apt/sources.list.d/debian.sources \
    || true

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    python3-dev \
    libffi-dev \
    libssl-dev \
    ca-certificates \
    bash \
    ffmpeg \
    libavcodec-extra \
    fonts-noto-cjk \
    curl \
    gnupg \
    git \
    ripgrep \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Dependency layer comes BEFORE the code copy so that everyday code
# changes hit the Docker cache here and skip the slow pip install.
# Only a pyproject.toml / uv.lock change rebuilds this layer.
COPY pyproject.toml uv.lock .python-version README.md ./

RUN python -m pip install uv -i https://mirrors.cloud.tencent.com/pypi/simple \
    && uv export --no-emit-project --format requirements.txt --output-file requirements.txt --frozen \
    && uv pip install -r requirements.txt --no-cache-dir --system \
        --index-url https://mirrors.cloud.tencent.com/pypi/simple \
    && uv pip install socksio uv pilk --no-cache-dir --system \
        --index-url https://mirrors.cloud.tencent.com/pypi/simple

COPY . /AstrBot/

EXPOSE 6185

CMD ["python", "main.py"]
