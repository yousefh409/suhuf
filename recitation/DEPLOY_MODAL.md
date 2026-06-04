# Deploying the recitation server to Modal

GPU service (REST `/api/score` + WebSocket `/ws/score`) on an L4, scale-to-zero.
Weights live on a Modal Volume; the image ships code only.

## Prerequisites

- A Modal account. `pip install modal` then `modal setup` (one-time browser auth).
- The model weights present locally under `recitation/models/` (gitignored, ~4GB):
  `ssl_xls_r_v5`, `xlsr_i3rab_contr`, `xlsr_contr1000`, `gmm/`,
  `error_classifier.pkl`, `type_classifier.pkl`. (Pull from the network volume / S3
  if missing — see the team notes on the `29p3s0lzcq` volume.)

## One-time setup

1. Auth: `modal setup`
2. Push weights to the Volume (creates it if missing):
   ```
   cd recitation
   bash scripts/upload_modal_weights.sh
   ```
3. Create the runtime secret (auth + CORS). `RECITATION_AUTH_SECRET` signs WS
   session tokens; `RECITATION_ALLOWED_ORIGINS` is the comma-separated web origin(s):
   ```
   modal secret create suhuf-recitation \
     RECITATION_AUTH_SECRET="$(openssl rand -hex 32)" \
     RECITATION_ALLOWED_ORIGINS="https://app.suhuf.example" \
     RECITATION_MAX_SESSION_SEC="600"
   ```

## Deploy

```
cd recitation
modal deploy modal_app.py
```

Prints a URL like `https://<org>--suhuf-recitation-serve.modal.run`. Endpoints:
- REST: `POST https://.../api/score`
- WebSocket: `wss://.../ws/score`
- Health/UI: `GET https://.../`

Point the web app at it (e.g. `NEXT_PUBLIC_RECITATION_WS=wss://.../ws/score`).
`RECITATION_ALLOWED_ORIGINS` must include the web origin or the WS handshake is rejected.

## Updating

- **Code** (engine/ensemble/server): `modal deploy modal_app.py` again.
- **Ensemble config / thresholds** (`ensemble_config.json`): it's in the image →
  redeploy. (To change without a redeploy, move it onto the Volume.)
- **Weights**: re-run `scripts/upload_modal_weights.sh` (uses `--force`), then redeploy
  to pick up a fresh container.

## Notes

- **GPU**: L4 (24GB) holds 3× XLS-R 300M + whisper-small comfortably. Cheaper `T4`
  works; bump `gpu=` in `modal_app.py` for more headroom.
- **Cold start**: container boot + loading 4 models from the Volume (~30-60s). Set
  `min_containers=1` in `modal_app.py` to eliminate it (you then pay to keep 1 warm).
- **Concurrency**: `@modal.concurrent(max_inputs=8)` per container; Modal autoscales
  containers beyond that. WebSocket sessions are long-lived — tune to GPU headroom.
- **The ensemble auto-activates** once all member weights are on the Volume; if any
  are missing it falls back to single-model `base` and logs (never crashes).
