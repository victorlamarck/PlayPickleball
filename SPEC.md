# SPEC — Pickleball Live Scores API

> **Para o humano (Victor):** crie uma pasta vazia, coloque este arquivo como `SPEC.md` na raiz, abra no VS Code e peça ao agente (Claude Code, Copilot Agent, Cursor etc.):
> *"Leia o SPEC.md inteiro e implemente o projeto fase por fase, parando ao fim de cada fase para eu revisar."*
> Revise cada fase antes de seguir. Você precisa entender cada decisão, porque o CTO vai perguntar.

---

## 0. Instruções para o agente de código

Você é um engenheiro sênior de backend construindo um projeto de portfólio. Siga estas regras:

1. **Todo código, comentários, commits, docstrings e o README devem estar em inglês.** Este SPEC está em português apenas para o dono do repositório.
2. Implemente **fase por fase** (seção 18). Ao final de cada fase: rode lint, type-check e testes, mostre o resultado e **pare** para revisão humana.
3. Prefira código simples, legível e idiomático a abstrações "espertas". É um projeto pequeno; não crie camadas que não pagam o próprio custo.
4. Nunca comite segredos. Nada de JSON de service account no repo. Use variáveis de ambiente e Application Default Credentials.
5. Use **type hints em tudo** e mantenha `mypy --strict` passando no pacote `app/`.
6. Quando uma decisão deste SPEC for ambígua, escolha a opção mais simples, registre-a em `docs/DECISIONS.md` e siga em frente.
7. Fixe as versões das dependências via lockfile (`uv.lock`). Use as versões estáveis mais recentes de cada biblioteca.
8. Não invente funcionalidades fora do escopo (seção 19).

---

## 1. Contexto e objetivo

Um app Flutter de torneios de pickleball precisa mostrar **placares ao vivo** num chaveamento (bracket) para centenas de espectadores simultâneos. O backend existente é **Python no Cloud Run**, com **Postgres** e **Firestore**.

Este projeto demonstra a arquitetura recomendada:

- **Postgres é a fonte da verdade.** Todas as escritas passam pela API Python, que valida as regras do jogo e grava no Postgres.
- **Firestore é o read model em tempo real.** Depois do commit, o estado da partida é espelhado num documento do Firestore (um por partida). Os clientes Flutter assinam esses documentos com snapshot listeners e recebem atualizações em menos de um segundo, sem conexões longas no Cloud Run.
- **Transactional outbox** garante que Postgres e Firestore não divirjam: o evento é gravado no outbox *na mesma transação* da mudança de placar, e um relay publica no Firestore com retry.
- **Writes com versão** garantem ordem: o Firestore só aceita um documento se a versão for maior que a armazenada, então uma publicação atrasada nunca sobrescreve uma mais nova.
- **FCM** (opcional, atrás de feature flag) envia push para eventos importantes ("partida começou", "resultado final").

---

## 2. Stack

| Área | Escolha |
|---|---|
| Linguagem | Python 3.12 |
| Gerenciador de pacotes | `uv` |
| Framework web | FastAPI + Uvicorn |
| Validação | Pydantic v2 + `pydantic-settings` |
| Banco | PostgreSQL 16 |
| ORM / driver | SQLAlchemy 2.x (async) + `asyncpg` |
| Migrations | Alembic |
| Read model | `google-cloud-firestore` (`AsyncClient`) |
| Push | `firebase-admin` (FCM), opcional |
| Logs | `structlog`, JSON em produção e legível no dev |
| Testes | `pytest`, `pytest-asyncio`, `httpx.AsyncClient` |
| Qualidade | `ruff` (lint + format), `mypy --strict` |
| Local | Docker Compose: Postgres + emulador do Firestore |
| Deploy | Dockerfile multi-stage → Cloud Run |
| CI | GitHub Actions |

---

## 3. Arquitetura

```mermaid
flowchart LR
    SK[Scorekeeper app / simulator] -- "POST score (API key)" --> API[FastAPI on Cloud Run]
    API -- "1 transaction: match + outbox row" --> PG[(Postgres)]
    API -- "after commit: best-effort publish" --> RELAY[Outbox relay]
    SCHED[Cloud Scheduler] -- "POST /internal/outbox/drain" --> RELAY
    RELAY -- "read pending (SKIP LOCKED)" --> PG
    RELAY -- "versioned write" --> FS[(Firestore read model)]
    RELAY -. "optional" .-> FCM[FCM topics]
    FS -- "snapshot listeners" --> APP[Flutter viewers x N]
```

### Fluxo de uma atualização de placar

1. O scorekeeper envia `POST /matches/{id}/points` com `expected_version`.
2. A API abre uma transação: `SELECT ... FOR UPDATE` na partida, confere a versão (`409` se divergir), aplica as regras de pontuação, incrementa `version` e insere uma linha no `outbox_events`. Faz commit.
3. Depois do commit, a API agenda a publicação via `BackgroundTasks` (caminho rápido, normalmente abaixo de 1s).
4. O relay lê os eventos pendentes com `FOR UPDATE SKIP LOCKED`, **agrupa por partida e mantém só a versão mais recente**, faz um write condicional no Firestore e marca os eventos como publicados.
5. Se a publicação falhar, o evento continua pendente e é reprocessado pelo endpoint de drain (chamado pelo Cloud Scheduler a cada minuto, ou pelo loop do relay em dev).
6. Os clientes Flutter recebem o snapshot atualizado.

---

## 4. Estrutura de pastas

```
.
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app factory, lifespan, routers
│   ├── config.py               # pydantic-settings
│   ├── logging.py              # structlog setup
│   ├── db.py                   # async engine/session
│   ├── models.py               # SQLAlchemy models
│   ├── schemas.py              # Pydantic request/response models
│   ├── auth.py                 # API key dependency
│   ├── errors.py               # domain exceptions + handlers
│   ├── domain/
│   │   ├── scoring.py          # pure pickleball scoring rules (no I/O)
│   │   └── bracket.py          # pure bracket generation/advancement (no I/O)
│   ├── services/
│   │   ├── tournaments.py
│   │   └── matches.py
│   ├── readmodel/
│   │   ├── projector.py        # Postgres state -> Firestore document dict
│   │   ├── firestore_publisher.py
│   │   └── notifier.py         # FCM (real) + LoggingNotifier (dev)
│   ├── outbox/
│   │   ├── relay.py            # drain logic, coalescing, retries
│   │   └── __main__.py         # `python -m app.outbox` -> local loop
│   └── routers/
│       ├── health.py
│       ├── tournaments.py
│       ├── matches.py
│       └── internal.py
├── migrations/                 # Alembic
├── scripts/
│   ├── seed.py                 # creates a demo 8-team tournament
│   └── simulate.py             # plays matches through the HTTP API
├── tests/
│   ├── unit/
│   └── integration/
├── firestore.rules
├── firebase.json               # emulator config (Firestore only)
├── client_flutter/             # Phase 6 (optional) demo viewer
├── docs/
│   ├── DECISIONS.md
│   └── SCALING.md
├── Dockerfile
├── docker-compose.yml
├── Makefile
├── .env.example
├── .github/workflows/ci.yml
├── pyproject.toml
└── README.md
```

---

## 5. Modelo de dados (Postgres)

Use UUID (`gen_random_uuid()`) como chave primária e `timestamptz` para datas.

**`tournaments`**
- `id`, `name`, `status` (`scheduled` | `in_progress` | `finished`), `created_at`, `updated_at`

**`teams`**
- `id`, `tournament_id` (FK), `name`, `seed` (int)
- unique (`tournament_id`, `seed`)

**`matches`**
- `id`, `tournament_id` (FK)
- `round` (int, 1 = primeira rodada), `position` (int, índice de 0 a n-1 dentro da rodada)
- `team_a_id`, `team_b_id` (FK nullable: rodadas futuras começam vazias)
- `status` (`pending` | `live` | `finished`)
- `games` (JSONB: lista de `{ "a": int, "b": int }`, até 3 itens)
- `winner_team_id` (nullable)
- `next_match_id` (FK para `matches`, nullable na final), `next_slot` (`A` | `B`, nullable)
- `version` (int, começa em 1, incrementa a cada mudança)
- `updated_at`
- unique (`tournament_id`, `round`, `position`)

**`outbox_events`**
- `id` (bigserial), `aggregate_type` (`match` | `tournament`), `aggregate_id` (uuid)
- `aggregate_version` (int), `event_type` (`match_updated`, `match_started`, `match_finished`, `tournament_updated`)
- `payload` (JSONB: o documento já projetado)
- `created_at`, `published_at` (nullable), `attempts` (int, default 0), `last_error` (text, nullable)
- índice parcial: `WHERE published_at IS NULL`

**`idempotency_keys`**
- `key` (text, PK), `request_hash` (text), `response_status` (int), `response_body` (JSONB), `created_at`
- Mesma chave com o mesmo hash devolve a resposta salva. Mesma chave com hash diferente devolve `422`.
- Limpeza: chaves com mais de 24h podem ser apagadas (documentar; um job de limpeza não é necessário).

---

## 6. Regras de domínio

Implemente em `app/domain/` como **funções puras, sem I/O**, com testes unitários extensivos.

### 6.1 Pontuação (simplificada, documentada no README)
- **Rally scoring** até 11, **vence quem abrir 2 de vantagem**, melhor de 3 games.
- `add_point(games, team) -> games` adiciona o ponto ao game atual. Ao fechar um game, abre o próximo se a partida não estiver decidida.
- `is_match_decided(games) -> winner | None`.
- Ponto em partida que não está `live` → erro de domínio (`409`).
- Correções: `set_game_score(games, game_index, a, b)` valida pontuações possíveis (não negativas; um game finalizado precisa ter um placar válido de vitória).
- Observação para o README: o pickleball real normalmente usa side-out scoring com número do sacador. Rally scoring foi escolhido para manter o foco na arquitetura em tempo real, e a regra está isolada em um módulo puro, fácil de trocar.

### 6.2 Chaveamento
- Eliminação simples. `POST /tournaments` aceita **4, 8 ou 16 times** (sem byes; documentar como fora de escopo).
- A primeira rodada é montada por seed: 1 vs n, 2 vs n-1, … em ordem padrão de chaveamento, para que os seeds 1 e 2 só se enfrentem na final.
- Cada partida conhece `next_match_id` e `next_slot`.
- Quando uma partida termina, na **mesma transação**: define `winner_team_id`, `status=finished`, coloca o vencedor no slot da próxima partida e incrementa a versão **das duas** partidas, gerando um outbox event para cada.
- Quando a final termina, o torneio vira `finished` e gera um `tournament_updated`.

---

## 7. API HTTP

Base: `/v1`. Todos os endpoints de escrita exigem o header `X-API-Key` (comparação em tempo constante). Todos os POST aceitam o header opcional `Idempotency-Key`.

| Método | Caminho | Auth | Descrição |
|---|---|---|---|
| GET | `/health` | não | liveness |
| GET | `/health/ready` | não | checa a conexão com o DB |
| POST | `/v1/tournaments` | sim | cria o torneio com times; gera o chaveamento |
| GET | `/v1/tournaments/{id}` | não | dados do torneio |
| GET | `/v1/tournaments/{id}/bracket` | não | todas as partidas agrupadas por rodada (fallback/estado inicial para clientes sem Firestore) |
| POST | `/v1/matches/{id}/start` | sim | `pending` → `live` (exige os dois times) |
| POST | `/v1/matches/{id}/points` | sim | body `{ "team": "A"\|"B", "expected_version": int }` |
| PUT | `/v1/matches/{id}/games/{index}` | sim | correção: `{ "a": int, "b": int, "expected_version": int }` |
| POST | `/internal/outbox/drain` | header `X-Internal-Token` | publica eventos pendentes; retorna `{published, failed, remaining}` |

### Respostas e erros
- As respostas de partida retornam a partida inteira, incluindo `version`.
- Formato de erro (todos os erros):
  ```json
  { "error": { "code": "version_conflict", "message": "...", "details": {} } }
  ```
- Códigos: `400/422` validação, `401` API key ausente ou inválida, `404` não encontrado, `409` `version_conflict` ou `invalid_state`.
- Num `409 version_conflict`, inclua a `current_version` em `details` para o cliente refazer a requisição.

### OpenAPI
- Títulos, descrições e exemplos nos schemas, para que `/docs` fique apresentável (recrutadores vão abrir).

---

## 8. Read model no Firestore

### 8.1 Documentos
- `tournaments/{tournamentId}`:
  ```json
  { "name": "...", "status": "in_progress", "rounds": 3, "version": 7, "updatedAt": <server timestamp> }
  ```
- `tournaments/{tournamentId}/matches/{matchId}` (**um documento por partida**: respeita o limite de cerca de 1 write/s por documento e mantém cada atualização pequena):
  ```json
  {
    "round": 1, "position": 0,
    "teamA": { "id": "...", "name": "...", "seed": 1 },
    "teamB": { "id": "...", "name": "...", "seed": 8 },
    "status": "live",
    "games": [ { "a": 11, "b": 7 }, { "a": 4, "b": 2 } ],
    "winnerTeamId": null,
    "version": 23,
    "updatedAt": <server timestamp>
  }
  ```
- `projector.py` é a **única** função que transforma o estado do Postgres no dict do documento. O payload do outbox é exatamente esse dict (sem o `updatedAt`, que é definido na publicação).

### 8.2 Write condicional com versão
Em `firestore_publisher.py`, use uma transação do Firestore: lê o documento atual; se `stored.version >= incoming.version`, pula (conta como sucesso/no-op); senão, grava. Isso torna a publicação **idempotente e segura contra ordem trocada**.

### 8.3 Security rules (`firestore.rules`)
- Qualquer um pode ler `tournaments/**` (espectadores podem estar deslogados; documentar que em produção isso poderia exigir Firebase Auth).
- **Nenhuma escrita de cliente.** Só o backend (Admin SDK / service account) grava.
- Inclua um teste das rules com o emulador se for simples; senão, documente.

---

## 9. Outbox relay

`app/outbox/relay.py` expõe `async def drain(batch_size: int = 200) -> DrainResult`:

1. Em uma transação: `SELECT ... FROM outbox_events WHERE published_at IS NULL ORDER BY id LIMIT :n FOR UPDATE SKIP LOCKED`.
2. **Agrupa** por (`aggregate_type`, `aggregate_id`): publica só o evento de maior `aggregate_version`. Os mais antigos do grupo são marcados como publicados (foram substituídos).
3. Publica com concorrência limitada (`asyncio.Semaphore`, ex.: 20).
4. Sucesso → `published_at = now()`. Falha → `attempts += 1`, `last_error = ...`, continua pendente.
5. Eventos `match_started` / `match_finished` também chamam o `Notifier` (tópico FCM `tournament_{id}`). Falha de notificação **não** bloqueia a publicação no Firestore (só loga).

Gatilhos:
- **Caminho rápido:** depois do commit, o endpoint de escrita agenda `drain()` via `BackgroundTasks`.
- **Rede de segurança:** `POST /internal/outbox/drain` (o Cloud Scheduler chama a cada minuto em produção).
- **Dev:** `python -m app.outbox` roda `drain()` em loop a cada 500ms até Ctrl+C.

Documente em `docs/DECISIONS.md` por que não há um loop em background dentro do serviço do Cloud Run: com CPU alocada só durante requisições, loops em background não são confiáveis. A alternativa seria CPU sempre alocada ou um worker separado, trocados aqui por simplicidade.

---

## 10. Concorrência e consistência

- Toda escrita de partida usa `SELECT ... FOR UPDATE` + checagem de `expected_version` na **mesma** transação.
- Mudança de partida e linhas de outbox são commitadas juntas, ou nenhuma é.
- Avanço de chaveamento trava as duas partidas em ordem determinística (por `id`) para evitar deadlocks.
- Uma camada de serviço retorna objetos de domínio; os routers não abrem transações sozinhos.

---

## 11. Configuração

`app/config.py` com `pydantic-settings`. `.env.example`:

```
ENV=dev                                  # dev | test | prod
DATABASE_URL=postgresql+asyncpg://scores:scores@localhost:5432/scores
GCP_PROJECT_ID=demo-live-scores
FIRESTORE_EMULATOR_HOST=localhost:8081   # unset in prod
API_KEY=dev-scorekeeper-key
INTERNAL_TOKEN=dev-internal-token
FCM_ENABLED=false
LOG_LEVEL=INFO
```

Em `prod`, falhe na inicialização se `API_KEY` ou `INTERNAL_TOKEN` estiverem com os valores padrão de dev.

---

## 12. Ambiente local

`docker-compose.yml`:
- `postgres` (16, healthcheck, volume)
- `firestore` (emulador, ex.: imagem `gcr.io/google.com/cloudsdktool/google-cloud-cli:emulators` com `gcloud emulators firestore start --host-port=0.0.0.0:8081`, project id `demo-live-scores`)
- `api` (opcional no compose; o fluxo normal de dev é rodar a API na máquina com `uv run`)

`Makefile` (com `help`):
```
make up         # docker compose up -d postgres firestore
make down
make migrate    # alembic upgrade head
make run        # uvicorn app.main:app --reload
make relay      # python -m app.outbox
make seed       # scripts/seed.py
make simulate   # scripts/simulate.py
make test       # pytest
make lint       # ruff check + ruff format --check + mypy
make fmt
```

Inclua uma seção **"Run it in 5 minutes"** no README, testada de ponta a ponta.

---

## 13. Scripts de demo

- `scripts/seed.py`: cria pela API um torneio de 8 times ("Demo Open") e imprime o tournament id e a URL do emulator UI/Firestore.
- `scripts/simulate.py --tournament <id> --speed 5`:
  - Inicia as partidas da primeira rodada, envia pontos aleatórios em paralelo (com `expected_version`; em `409`, rebusca e tenta de novo) e avança rodada por rodada até a final.
  - `--speed` = pontos por segundo por partida.
  - Imprime um log compacto no terminal.
  - É isso que vai mostrar as atualizações ao vivo na demo.

---

## 14. Testes

**Unitários (`tests/unit`)**, rápidos, sem I/O:
- Pontuação: vitória com 11-9, deuce (11-10 continua, 12-10 vence), melhor de 3 decidido em 2 ou em 3 games, ponto depois da partida decidida dá erro, validação de correções.
- Chaveamento: pares por seed para 4/8/16 times, ligação `next_match`/`next_slot`, avanço do vencedor.
- Agrupamento do relay (função pura que recebe eventos e devolve o que publicar).
- Projector: estado → formato do documento.

**Integração (`tests/integration`)**, com o Postgres e o emulador do compose:
- Criar torneio → GET bracket.
- Iniciar partida, marcar pontos, terminar partida → vencedor avança; os dois documentos no Firestore são atualizados com versões crescentes.
- **Concorrência:** duas requisições simultâneas com o mesmo `expected_version` → exatamente um `200` e um `409`.
- **Idempotência:** mesmo `Idempotency-Key` duas vezes → um único ponto aplicado, mesma resposta.
- **Ordem trocada:** publicar a versão 5 e depois a 4 → o Firestore mantém a 5.
- **Falha do relay:** simular uma exceção no publisher → evento continua pendente com `attempts=1`; o próximo drain publica.
- Auth: escrita sem `X-API-Key` → `401`.

Meta: os módulos de domínio com cobertura alta; não persiga cobertura nos routers.

---

## 15. Qualidade e CI

- `pyproject.toml` com configuração de `ruff` (regras: `E,F,I,B,UP,SIM,ASYNC`), `mypy --strict` em `app/` e `pytest`.
- `.github/workflows/ci.yml`: no push/PR, roda o lint, sobe Postgres como service container e o emulador do Firestore, roda migrations e testes. Cache do `uv`.
- Badge de CI no topo do README.

---

## 16. Deploy no Cloud Run

- `Dockerfile` multi-stage: build com `uv`, runtime `python:3.12-slim`, usuário não-root, `CMD` com uvicorn na porta `$PORT`.
- Migrations: rodar como **Cloud Run Job** (`alembic upgrade head`) antes de cada deploy; documentar.
- `docs/DEPLOY.md` com comandos `gcloud` passo a passo:
  - Cloud SQL Postgres (ou qualquer Postgres) + conexão via Cloud SQL connector ou URL pública com SSL.
  - Banco Firestore em modo Native.
  - Service account com `roles/datastore.user` (+ `roles/firebasemessaging.admin` se usar FCM); **sem arquivos de chave**, só a identidade do Cloud Run.
  - Segredos (`API_KEY`, `INTERNAL_TOKEN`, `DATABASE_URL`) no Secret Manager.
  - Job do Cloud Scheduler chamando `/internal/outbox/drain` a cada minuto com `X-Internal-Token`.
  - `firebase deploy --only firestore:rules`.
- O deploy em si é manual (documentado). A CI não faz deploy.

---

## 17. README (em inglês) — conteúdo obrigatório

1. Uma linha sobre o problema + badge de CI.
2. Diagrama de arquitetura (o mermaid da seção 3).
3. **Why this design**: Postgres como fonte da verdade, Firestore como read model em tempo real, outbox, writes com versão, documento por partida.
4. **Alternatives considered**: polling (+CDN), SSE/WebSockets no Cloud Run, FCM como canal principal, pub/sub gerenciado (Ably/Pusher/Centrifugo). Um parágrafo curto para cada com prós e contras.
5. **Scaling notes** (detalhes em `docs/SCALING.md`):
   - **Centenas a ~2k espectadores:** este design como está; custo desprezível.
   - **~200k espectadores:** o custo de leitura do Firestore cresce linearmente (atualizações × espectadores), então: agrupar atualizações em janelas de 1–2s, manter os documentos pequenos, considerar um documento de resumo do chaveamento lido uma vez e documentos por partida só para as partidas ao vivo que o usuário está olhando, e reavaliar um serviço de pub/sub dedicado. Inclua uma estimativa de custo simples, com a fórmula escrita (não só o número) e nota de que os preços variam por região.
6. **Run it in 5 minutes** (local).
7. **API overview** + link para `/docs`.
8. **Testing** (o que é coberto, como rodar).
9. **Simplifications / out of scope** (rally scoring, sem byes, auth por API key em vez de Firebase Auth + roles, etc.).
10. **What I'd do next in production** (Firebase Auth com custom claims para scorekeepers, rate limiting, tracing com OpenTelemetry, dead-letter de eventos com muitas tentativas, alertas).

Tom: claro e objetivo, como uma decisão de engenharia escrita para colegas. Sem linguagem de marketing.

---

## 18. Fases e critérios de aceite

**Fase 1: Esqueleto**
- `pyproject` com uv, layout de pastas, config, logging, `/health`, Dockerfile, compose, Makefile, CI rodando lint + um teste trivial.
- ✅ `make up && make run` → `/health` responde 200; CI verde.

**Fase 2: Domínio puro**
- `domain/scoring.py`, `domain/bracket.py` + testes unitários completos.
- ✅ `make test` verde; `mypy --strict` limpo.

**Fase 3: Persistência e API**
- Models, migration Alembic, services, routers, auth, erros, idempotência, controle de versão otimista, outbox gravado na mesma transação.
- ✅ Testes de integração de fluxo, concorrência, idempotência e auth passando (o Firestore ainda pode ser um fake em memória).

**Fase 4: Read model em tempo real**
- Projector, publisher do Firestore com write condicional, relay com agrupamento, endpoint de drain, `python -m app.outbox`, notifier (logging em dev, FCM atrás de flag), `firestore.rules`.
- ✅ Testes de integração contra o emulador, incluindo ordem trocada e falha + retry.

**Fase 5: Demo e docs**
- `seed.py`, `simulate.py`, README completo, `docs/DECISIONS.md`, `docs/SCALING.md`, `docs/DEPLOY.md`.
- ✅ Um desenvolvedor novo segue o "Run it in 5 minutes" e vê, na UI do emulador do Firestore, os documentos das partidas mudando enquanto o simulador roda.

**Fase 6 (opcional, recomendada): Visualizador Flutter**
- `client_flutter/`: app Flutter mínimo (Material 3) que se conecta ao emulador do Firestore (`useFirestoreEmulator`), lista as rodadas do torneio e mostra cada partida com `StreamBuilder` sobre `snapshots()`. Destaque visual rápido (ex.: animação curta) quando o placar muda. Sem login. Sem gerenciamento de estado pesado: `StreamBuilder` basta.
- ✅ Com o simulador rodando, o app mostra os placares atualizando ao vivo. Adicione um GIF curto disso no topo do README (gravado pelo humano; deixe um placeholder).

---

## 19. Fora de escopo

- Interface do scorekeeper (o simulador faz esse papel).
- Contas de usuário, Firebase Auth, papéis.
- Byes, dupla eliminação, fase de grupos, side-out scoring.
- Multi-região, cache em CDN, testes de carga (mencionar em SCALING.md como próximos passos).
- Painel admin.
