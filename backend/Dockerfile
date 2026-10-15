FROM python:3.11-slim

WORKDIR /app

# ── System dependencies ────────────────────────────────────────────────────────
# libgomp1: OpenMP runtime required by XGBoost CPU builds
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 \
 && rm -rf /var/lib/apt/lists/*

# ── Copy requirements first (cache-friendly layer) ─────────────────────────────
COPY backend/requirements.txt backend/requirements.txt

# ── Install all dependencies in a single step ──────────────────────────────────
#
# Why --extra-index-url instead of --index-url?
#   torch==2.5.1+cpu is pinned in requirements.txt and only exists on the
#   PyTorch CPU wheel index. Using --extra-index-url lets pip find that wheel
#   there while pulling everything else from the default PyPI index.
#
# Why --timeout 300 --retries 10?
#   The PyTorch CDN (download-r2.pytorch.org) is occasionally slow; generous
#   timeout + retries prevents transient network blips from aborting the build.
#
# Why no separate torch pre-install step?
#   A separate step timed out repeatedly. One combined install is more resilient
#   because pip resolves the full graph once and downloads in parallel.
#
RUN pip install --no-cache-dir \
      --timeout 300 \
      --retries 10 \
      --extra-index-url https://download.pytorch.org/whl/cpu \
      -r backend/requirements.txt

# NOTE: pip check intentionally omitted.
# The torch+cpu wheel can trigger false-positive conflicts in pip check
# (missing nvidia_* extras) that do not affect CPU-only runtime.

# ── Copy source code after pip (code changes don't bust the dep layer) ─────────
COPY . .

# ── Health check ───────────────────────────────────────────────────────────────
# start-period=90s: sentence-transformers downloads model weights on first import
# which can take 30-60 s inside a fresh container.
HEALTHCHECK --interval=30s --timeout=15s --start-period=90s --retries=5 \
  CMD python -c "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/v1/health', timeout=10).getcode() == 200 else 1)" || exit 1

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
