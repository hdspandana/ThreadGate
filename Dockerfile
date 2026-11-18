FROM python:3.13-slim@sha256:d98cc29d3266e535dd9da1099688d9cb3ca4753813571e071763d17725460962
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    HOME=/tmp THREADGATE_WORKSPACE_DB=/data/workspace.sqlite3
WORKDIR /opt/threadgate
COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock \
    && groupadd --gid 10001 threadgate \
    && useradd --uid 10001 --gid 10001 --no-create-home threadgate \
    && mkdir /data && chown 10001:10001 /data
COPY --chown=10001:10001 . .
USER 10001:10001
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health',timeout=4)"
CMD ["python", "scripts/serve.py", "--no-install"]
