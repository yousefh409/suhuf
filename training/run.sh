#!/bin/bash
# ============================================================
# One-command PCD fine-tuning on ClArTTS
# 
# Run this on a GPU server (RunPod, Lambda, Vast.ai, etc.)
# Estimated time: ~2-3 hours total (download + train + eval)
# Estimated cost: ~$2-3 on a $1/hr A100
#
# Usage:
#   git clone <your-repo> && cd i3rab
#   bash training/run.sh
#
# Or on RunPod:
#   1. Create a Pod with PyTorch template + A100 GPU
#   2. SSH in, clone repo, run this script
# ============================================================

set -e

echo "========================================"
echo "  PCD Fine-tuning Pipeline"
echo "  Target: General Arabic diacritics"
echo "========================================"

# ── Check GPU ──
if ! command -v nvidia-smi &> /dev/null; then
    echo "ERROR: No GPU detected. This script requires a CUDA GPU."
    exit 1
fi
echo "GPU detected:"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
echo ""

# ── Install dependencies ──
echo "[1/5] Installing dependencies..."
pip install -q --upgrade pip
pip install -q \
    'nemo_toolkit[asr]>=2.0.0' \
    pytorch-lightning \
    omegaconf \
    datasets \
    soundfile \
    scipy \
    numpy \
    huggingface_hub

# ── Prepare data ──
echo ""
echo "[2/5] Preparing data (ClArTTS + MUSAN noise + speed perturbation)..."
python training/prepare_data.py --output-dir data/

# ── Fine-tune ──
echo ""
echo "[3/5] Fine-tuning PCD on ClArTTS..."

# Auto-detect GPU memory and set batch size
GPU_MEM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1 | tr -d ' ')
if [ "$GPU_MEM" -gt 60000 ]; then
    BATCH_SIZE=32
    PRECISION="bf16-mixed"
    ACCUMULATE=2
    echo "  Detected >60GB VRAM (A100 80GB/H100) → batch=32, bf16"
elif [ "$GPU_MEM" -gt 35000 ]; then
    BATCH_SIZE=16
    PRECISION="bf16-mixed"
    ACCUMULATE=4
    echo "  Detected >35GB VRAM (A100 40GB) → batch=16, bf16"
elif [ "$GPU_MEM" -gt 20000 ]; then
    BATCH_SIZE=8
    PRECISION="16-mixed"
    ACCUMULATE=8
    echo "  Detected >20GB VRAM (RTX 4090/A5000) → batch=8, fp16"
else
    BATCH_SIZE=4
    PRECISION="32"
    ACCUMULATE=16
    echo "  Detected ≤20GB VRAM → batch=4, fp32 (will be slow)"
fi

python training/finetune_pcd.py \
    --data-dir data/ \
    --output-dir checkpoints/ \
    --epochs 20 \
    --batch-size $BATCH_SIZE \
    --precision $PRECISION \
    --accumulate-grad $ACCUMULATE \
    --lr 3e-5 \
    --freeze-encoder-epochs 5

# ── Evaluate ──
echo ""
echo "[4/5] Evaluating fine-tuned model..."
python training/evaluate.py \
    --model checkpoints/pcd_clartts_final.nemo \
    --data-dir data/ \
    --decoder ctc

# ── Upload to HuggingFace (optional) ──
echo ""
echo "[5/5] Done! Model saved to checkpoints/pcd_clartts_final.nemo"
echo ""
echo "To upload to HuggingFace Hub:"
echo "  huggingface-cli login"
echo "  python -c \""
echo "from huggingface_hub import HfApi"
echo "api = HfApi()"
echo "api.upload_file("
echo "    path_or_fileobj='checkpoints/pcd_clartts_final.nemo',"
echo "    path_in_repo='pcd_clartts_final.nemo',"
echo "    repo_id='YOUR_USERNAME/pcd-clartts-arabic-diacritics',"
echo "    repo_type='model',"
echo ")"
echo "\""
echo ""
echo "To download back to your Mac:"
echo "  scp <server>:~/i3rab/checkpoints/pcd_clartts_final.nemo ."
echo ""
echo "Total cost estimate: ~\$2-3 on an A100 at \$1/hr"
