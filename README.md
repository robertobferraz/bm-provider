# bm-provider

Provider HTTP externo para resolver playlists do Spotify por um caminho frontend-like e devolver um payload simples para o `music-bot` consumir por HTTP.

## Objetivo
Quando a Spotify Web API oficial retorna `403` em `/playlists/{id}/items`, este serviço tenta listar a playlist usando `SpotAPI` e converte o resultado para um contrato estável:

```json
{
  "items": [
    {
      "title": "P do Pecado - Ao Vivo",
      "artist": "Grupo Menos É Mais, Simone Mendes",
      "artists": ["Grupo Menos É Mais", "Simone Mendes"],
      "duration_ms": 192367,
      "isrc": "BRRGE2500260",
      "spotify_url": "https://open.spotify.com/track/7EknynLJTt9YMm1HL37s5D"
    }
  ],
  "total": 203,
  "invalid_items": 0
}
```

O bot principal não depende de `SpotAPI` diretamente. Ele fala com este serviço via HTTP.

## Endpoints
- `GET /health`
- `GET /resolve?url=<spotify_url>&kind=playlist&limit=10`

## Variáveis de ambiente
```env
BM_PROVIDER_HOST=0.0.0.0
BM_PROVIDER_PORT=8081
BM_PROVIDER_AUTH_TOKEN=
BM_PROVIDER_LANGUAGE=en
BM_PROVIDER_PUBLIC_ONLY=true
BM_PROVIDER_LOG_LEVEL=INFO
```

Se `BM_PROVIDER_AUTH_TOKEN` estiver preenchido, o serviço exige:

```text
Authorization: Bearer <token>
```

## Executar localmente
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m bm_provider.app
```

Teste:
```bash
curl -s http://127.0.0.1:8081/health
curl -s "http://127.0.0.1:8081/resolve?url=https://open.spotify.com/playlist/4CNxQ6HyaMjtHdWmJJb5Dx&kind=playlist&limit=3"
```

## Docker
Build:
```bash
docker build -t bm-provider:latest .
```

Run:
```bash
docker run --rm -p 8081:8081 \
  -e BM_PROVIDER_HOST=0.0.0.0 \
  -e BM_PROVIDER_PORT=8081 \
  bm-provider:latest
```

## Docker Compose
Subir com compose:
```bash
docker compose up -d --build
```

Parar:
```bash
docker compose down
```

Porta publicada no host por padrao:
```text
http://127.0.0.1:18081
```

Exemplo de healthcheck:
```bash
curl -s http://127.0.0.1:18081/health
```

Exemplo de resolve:
```bash
curl -s "http://127.0.0.1:18081/resolve?url=https://open.spotify.com/playlist/4CNxQ6HyaMjtHdWmJJb5Dx&kind=playlist&limit=3"
```

## Integração com o music-bot
No `.env` do bot:

```env
SPOTIFY_FRONTEND_FALLBACK=true
SPOTIFY_FRONTEND_PROVIDER_URL=http://bm-provider:8081/resolve
SPOTIFY_FRONTEND_PROVIDER_TOKEN=
```

Se proteger o provider, use o mesmo segredo dos dois lados:

```env
SPOTIFY_FRONTEND_PROVIDER_TOKEN=segredo
BM_PROVIDER_AUTH_TOKEN=segredo
```

## Observações
- Este serviço é separado do repo do bot por design.
- Ele depende de uma biblioteca que usa superfície privada/frontend-like do Spotify.
- Trate isso como integração frágil e opcional.
