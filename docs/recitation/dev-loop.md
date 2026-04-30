# Recitation dev loop

End-to-end loop for working on the recitation ↔ reader integration.

## Prereqs

- `recitation/models/ssl_xls_r_v5/` — fine-tuned XLS-R weights.
- A tashkeeled chapter dumped under `web/data/` (see [docs/reader/dev-loop.md](../reader/dev-loop.md)).
- Python deps: `pip install -r recitation/requirements.txt pytest pytest-asyncio websockets`.
- Web deps: `cd web && npm install`.

## Run both

```
# Terminal 1
cd recitation && python -m uvicorn server:app --host 0.0.0.0 --port 8000

# Terminal 2
cd web && npm run dev
```

Open `http://localhost:3000/internal/reader/<openiti_id>/<ch_index>`, allow mic, tap **Recite**.

## Tests

```
# Engine + protocol
cd recitation && python -m pytest test_inline_passage.py test_extend_phrases.py test_retreat.py test_auth.py -v

# Reader library
cd web && npm run test -- recitation
```

## Production env (preview)

| Var (server) | Default | Effect |
|---|---|---|
| `RECITATION_AUTH_SECRET` | unset | Require valid HMAC token if set |
| `RECITATION_ALLOWED_ORIGINS` | unset | Comma-separated allowlist |
| `RECITATION_ALLOW_DEBUG` | `0` | Permit `debug:true` audio dumps |
| `RECITATION_MAX_SESSION_SEC` | `600` | Per-session hard cap |
| `LOG_STREAMING` | `0` | Emit JSON-line logs per cycle |

| Var (reader) | Default | Effect |
|---|---|---|
| `NEXT_PUBLIC_RECITATION_WS_URL` | `ws://localhost:8000/ws/score` | WS endpoint |
| `RECITATION_AUTH_SECRET` | unset | Same secret as server (for token mint) |
| `RECITATION_TOKEN_TTL_SEC` | `300` | JWT TTL |

## Deploying the recitation server

1. Build the image: `docker build -t suhuf-recitation recitation/`.
2. Push to your registry of choice.
3. Run on a GPU host (Modal / Railway-with-GPU / RunPod). Mount or bake `models/ssl_xls_r_v5/`.
4. Front it with a TLS-terminating proxy (Caddy / nginx / Cloudflare) so the WS upgrade is `wss://`.
5. Set the reader's `NEXT_PUBLIC_RECITATION_WS_URL` to that URL.
6. Set the same `RECITATION_AUTH_SECRET` on both sides.
7. Set `RECITATION_ALLOWED_ORIGINS=https://<reader-domain>` on the server.
