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
    nodejs \
    npm \
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

# Claude Code engine (official CLI, headless). Own layer: only rebuilds when
# the CLI install line changes. npmmirror keeps this fast from CN VPSes.
RUN npm install -g --registry=https://registry.npmmirror.com @anthropic-ai/claude-code \
    && npm cache clean --force

# Bootstrap Claude Code home on every start: mark onboarding done (headless
# runs skip the interactive wizard), and keep skills on the persistent data
# volume so engine-visible skills survive container recreation.
CMD mkdir -p /root/.claude /AstrBot/data/skills \
    && { [ -f /root/.claude.json ] || printf '{"hasCompletedOnboarding":true,"theme":"dark"}' > /root/.claude.json; } \
    && ln -sfn /AstrBot/data/skills /root/.claude/skills \
    && python main.py

EXPOSE 6185
