"""Modal deployment for the recitation server (REST + WebSocket, GPU).

Serves the existing FastAPI app (server.py) on an L4 GPU. Model weights live on a
Modal Volume (not baked into the image) so the image stays small and weights are
updated independently. Whisper (position tracking) is cached on a second Volume.

Deploy: see DEPLOY_MODAL.md. TL;DR:
  modal setup                                   # one-time auth
  bash scripts/upload_modal_weights.sh          # push weights to the Volume
  modal secret create suhuf-recitation ...      # auth secret + allowed origins
  modal deploy modal_app.py                      # -> https://<org>--suhuf-recitation-serve.modal.run
"""
import modal
from pathlib import Path

REC_DIR = Path(__file__).parent
APP_DIR = "/app"
MODELS_DIR = "/app/models"      # Volume mounts here -> server.py's BASE_DIR/models resolves
HF_CACHE = "/cache/hf"

# Pinned scikit-learn to match the pickled error/type classifiers (built on 1.7.x);
# loading them under a very different version warns and can break.
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .pip_install(
        "fastapi[standard]",
        "python-multipart",
        "torch",
        "torchaudio",
        "transformers",
        "numpy",
        "scikit-learn==1.7.2",
        "soundfile",
        "librosa",
        "huggingface_hub",
    )
    .env({"HF_HOME": HF_CACHE})
    # ship the code only; weights come from the Volume
    .add_local_dir(
        str(REC_DIR),
        remote_path=APP_DIR,
        ignore=[
            "models/**", "test_data/**", "data/**", "training/**",
            "**/__pycache__/**", "*.pyc", "*.nemo", "*.ckpt", "*.log",
            "modal_app.py", "tune_ensemble.py", "eval*.py", "eval_*.json",
            "fp_diag.py", "test_*.py", "EXPLORE_NOTES.md",
        ],
    )
)

app = modal.App("suhuf-recitation")
models_vol = modal.Volume.from_name("suhuf-recitation-models", create_if_missing=True)
hf_vol = modal.Volume.from_name("suhuf-recitation-hf-cache", create_if_missing=True)


@app.function(
    image=image,
    gpu="L4",                       # 24GB: 3x XLS-R 300M + whisper-small fit easily
    volumes={MODELS_DIR: models_vol, HF_CACHE: hf_vol},
    secrets=[modal.Secret.from_name("suhuf-recitation")],
    scaledown_window=300,           # keep warm 5 min after last request (avoid reloading 4 models)
    timeout=600,
    min_containers=0,               # scale to zero; set 1 to kill cold starts (costs more)
)
@modal.concurrent(max_inputs=8)     # concurrent REST/WS connections per GPU container
@modal.asgi_app()
def serve():
    import os, sys
    sys.path.insert(0, APP_DIR)
    os.chdir(APP_DIR)               # so BASE_DIR / relative paths resolve under /app
    from server import app as web_app   # FastAPI startup loads the ensemble from the Volume
    return web_app
