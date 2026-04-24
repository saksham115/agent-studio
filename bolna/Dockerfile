FROM python:3.10.13-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libgomp1 git ffmpeg gcc g++ python3-dev build-essential && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip setuptools wheel

RUN pip install git+https://github.com/bolna-ai/bolna@master

# Smart-turn-v3 semantic turn-detection — inference-only deps (ONNX, no torch).
# Adds ~250 MB to the image. Model weights (~32 MB) are fetched from
# HuggingFace separately below.
RUN pip install --no-cache-dir \
      "onnxruntime>=1.19" \
      "transformers>=4.44" \
      "numpy>=1.26" \
      "pytest>=8.0" \
    && apt-get update && apt-get install -y --no-install-recommends curl \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Fetch smart-turn-v3.2 CPU-optimized ONNX weights (BSD-2-Clause, Daily Inc).
# HuggingFace ships separate CPU and GPU variants; we run on CPU in the
# sidecar. Path must match SMART_TURN_MODEL_PATH in smart_turn.py.
RUN mkdir -p /opt/smart-turn && \
    curl -fsSL -o /opt/smart-turn/smart-turn-v3.2-cpu.onnx \
      https://huggingface.co/pipecat-ai/smart-turn-v3/resolve/main/smart-turn-v3.2-cpu.onnx

COPY smart_turn.py /app/
COPY server.py /app/

EXPOSE 5001

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "5001"]
