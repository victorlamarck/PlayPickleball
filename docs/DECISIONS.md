# Decisões e registro de mudanças

Este arquivo registra **cada mudança feita no projeto e o motivo**, fase por fase, além das decisões
tomadas onde o SPEC era ambíguo. Ele é escrito em português a pedido do dono do repositório, o que
abre uma exceção à regra 1 do SPEC. Código, comentários, commits e o README continuam em inglês.

---

## Fase 1 — Esqueleto

### Mudanças

| # | O quê | Por quê |
|---|---|---|
| 1.1 | Instalado o `uv` com `pip install --user`, e o Python 3.12.15 via `uv python install 3.12` | O SPEC exige `uv` e Python 3.12. A máquina só tinha o Python 3.14. O `uv` baixa o 3.12 isolado, sem mexer no Python do sistema. |
| 1.2 | `pyproject.toml` sem `[build-system]` (projeto "virtual" do uv) | É uma aplicação, não uma biblioteca publicada. Sem build-system, o `uv sync` só instala as dependências, e o código roda direto da pasta `app/`. Fica mais simples, inclusive no Docker. |
| 1.3 | `requires-python = ">=3.12,<3.13"` e `.python-version` com `3.12` | Garante que dev, CI e Docker usem a mesma versão menor do Python. |
| 1.4 | Ruff com as regras `E,F,I,B,UP,SIM,ASYNC` e linha de 100 caracteres | As regras são as pedidas no SPEC (seção 15). Os 100 caracteres são um meio-termo comum e legível. |
| 1.5 | `extend-immutable-calls` para `Depends`/`Header`/`Query`/`Path` no Ruff | A regra `B008` reclamaria do padrão do FastAPI de chamar funções nos valores padrão dos argumentos. Essa é a forma oficial de silenciar só esses casos. |
| 1.6 | `mypy --strict` com o plugin do Pydantic, aplicado ao pacote `app` | O SPEC exige strict em `app/`. O plugin faz o mypy entender os construtores dos models Pydantic. |
| 1.7 | `pytest-asyncio` em `asyncio_mode = "auto"` com o event loop por sessão | No modo auto, os testes `async def` não precisam do decorator. Um loop único por sessão evita erros de "loop fechado" quando houver engine/cliente compartilhado entre testes (Fase 3). |
| 1.8 | `app/config.py` com `pydantic-settings`, carregado via `get_settings()` com `lru_cache` | Lê as variáveis de ambiente e o `.env`, e o cache evita reler a cada requisição. Em `prod`, a aplicação **falha na inicialização** se `API_KEY` ou `INTERNAL_TOKEN` estiverem com os valores de dev (exigência da seção 11 do SPEC, coberta por teste). |
| 1.9 | `app/logging.py` com `structlog`: JSON em `prod`, console colorido em dev/test | Exigência do SPEC. No Cloud Run, JSON em stdout vira log estruturado automaticamente. |
| 1.10 | `create_app()` como fábrica, mais `app = create_app()` no módulo | A fábrica permite criar apps isolados nos testes. A variável `app` é o que o `uvicorn app.main:app` usa. |
| 1.11 | Só o `GET /health` nesta fase | O `/health/ready` verifica o banco, então entra na Fase 3 junto com `app/db.py`. |
| 1.12 | `Dockerfile` multi-stage: `uv sync --frozen --no-dev` no build, `python:3.12-slim` no runtime, usuário `appuser` (uid 10001) | Imagem final pequena, sem as ferramentas de build, rodando como usuário não-root (SPEC, seção 16). As dependências são instaladas antes de copiar o código, para aproveitar o cache de camadas do Docker. A porta vem de `$PORT`, que o Cloud Run injeta. |
| 1.13 | O `Dockerfile` ainda não copia `migrations/` e `alembic.ini` | Esses arquivos ainda não existem, e o `COPY` quebraria o build. As linhas voltam na Fase 3. |
| 1.14 | `docker-compose.yml` com `postgres:16` (healthcheck + volume), o emulador do Firestore na porta 8081 e o serviço `api` no profile `api` | Com o profile, o `make up` sobe só o Postgres e o emulador (o fluxo normal de dev roda a API com `uv run`). Para subir a API em container: `docker compose --profile api up`. |
| 1.15 | `make up` usa `docker compose up -d --wait` | O `--wait` só retorna quando os serviços estão saudáveis, então `make up && make migrate` não falha por corrida. |
| 1.16 | `Makefile` com `help` autodocumentado (comentários `##`) | O SPEC pede um alvo `help`, e assim ele nunca fica desatualizado. |
| 1.17 | O `make` não foi instalado no Windows | O Makefile é o ponto de entrada oficial (a CI roda Linux). No Windows, cada alvo é um comando `uv run ...` ou `docker compose ...` de uma linha, que dá para rodar direto. |
| 1.18 | CI (`.github/workflows/ci.yml`) com `astral-sh/setup-uv` e cache habilitado, rodando `make lint` e `make test` | É o pedido da Fase 1. Os service containers (Postgres e emulador) entram quando houver testes de integração (Fases 3 e 4). |
| 1.19 | `.gitignore` bloqueia `.env` e qualquer `service-account*.json` / `*.json.key` | Regra 4 do SPEC: nunca comitar segredos. |
| 1.20 | `git init` na branch `main`, **sem commit** | Os commits ficam a critério do dono do repositório, depois da revisão. |
| 1.21 | O badge de CI no README usa `OWNER/REPO` como placeholder | O repositório no GitHub ainda não existe. Trocar pelo caminho real. |

---

## Fase 2 — Domínio puro

### Mudanças

| # | O quê | Por quê |
|---|---|---|
| 2.1 | `app/errors.py` com `DomainError` (que carrega `code`, `status_code`, `message` e `details`) e as subclasses `InvalidStateError` (409), `InvalidScoreError` (422) e `InvalidBracketError` (422) | O SPEC define o formato de erro `{code, message, details}`. Com as exceções carregando esses campos, o handler HTTP da Fase 3 fica trivial. O arquivo não importa o FastAPI, então o domínio continua puro. |
| 2.2 | Placar representado por `GameScore(a, b)`, um dataclass imutável (`frozen`, `slots`) | Mais seguro que dicts soltos: o mypy verifica os tipos, e a imutabilidade impede bugs de mutação acidental. A conversão de/para o JSONB `{ "a", "b" }` fica na persistência (Fase 3). |
| 2.3 | As funções de pontuação recebem uma sequência e **retornam uma lista nova**, sem alterar a entrada | É o que define uma função pura: fácil de testar e sem efeitos colaterais escondidos (há teste garantindo isso). |
| 2.4 | Constantes `POINTS_TO_WIN=11`, `WIN_BY=2` e `GAMES_TO_WIN=2` | A regra fica explícita e fácil de trocar (o SPEC pede o módulo isolado para uma futura troca por side-out scoring). |
| 2.5 | O `add_point` abre o próximo game (0-0) assim que um game fecha, se a partida não estiver decidida | É o comportamento descrito no SPEC (6.1). Assim o cliente vê o novo game aberto imediatamente. |
| 2.6 | Ponto em partida já decidida → `InvalidStateError` (409) | SPEC 6.1. A regra "partida precisa estar `live`" depende do status, que fica no banco, então é verificada na camada de serviço (Fase 3). |
| 2.7 | Regra de placar possível: um game em andamento aceita qualquer placar sem vencedor (ex.: 20-19), e um game finalizado precisa parar **exatamente** no ponto da vitória: `vencedor == max(11, perdedor + 2)` | É a interpretação de "um game finalizado precisa ter um placar válido de vitória". Assim 11-9, 12-10 e 16-14 são válidos, e 15-3, 12-9 e 13-10 são impossíveis (o game teria acabado antes). |
| 2.8 | `validate_games` verifica a lista inteira: no máximo 3 games, só o último pode estar em andamento e nenhum game pode vir depois da partida já decidida | Uma correção num game do meio pode deixar o estado global inconsistente, e validar a lista inteira cobre todos os casos com uma regra só. |
| 2.9 | Se uma correção decide a partida e o último game está 0-0, esse game vazio é removido. Se o game posterior já tem pontos, a correção é rejeitada (422) | O game 0-0 só existia porque a partida "ainda não tinha acabado", então removê-lo é seguro. Já um game com pontos indica erro do scorekeeper, que deve ser resolvido explicitamente. |
| 2.10 | O `add_point` também abre um game novo se o último já está fechado (não só depois de pontuar) | É uma defesa para listas vindas de correções ou dados antigos sem o game aberto. O comportamento fica previsível. |
| 2.11 | Partidas do chaveamento identificadas por `(round, position)` no domínio, sem UUIDs | Mantém o domínio puro e determinístico. A camada de serviço (Fase 3) traduz `(round, position)` → `next_match_id`. |
| 2.12 | Ordem padrão de seeds gerada recursivamente (`[1]` → `[1,2]` → `[1,4,2,3]` → `[1,8,4,5,2,7,3,6]`…) | Os pares de cada rodada somam n+1 (1 vs n, 2 vs n-1…), e os seeds 1 e 2 caem em metades opostas, então só se enfrentam na final (exigência do SPEC 6.2, coberta por teste). |
| 2.13 | O vencedor de `(r, p)` vai para `(r+1, p // 2)`, no slot A se `p` é par e B se ímpar | É a fórmula padrão de árvore binária: simples, sem tabela de ligação, e verificada em teste para 4, 8 e 16 times. |
| 2.14 | `place_winner` é idempotente para o mesmo time e rejeita (409) sobrescrever um time diferente | A idempotência protege contra reprocessamento. A rejeição impede corromper o chaveamento se uma partida anterior for "re-finalizada" com outro vencedor. |
| 2.15 | `MatchTeams[T]` genérico (sintaxe PEP 695 do Python 3.12) | O mesmo código serve para seeds (`int`) nos testes e para UUIDs no serviço, sem `Any`. |
| 2.16 | Contagens de times aceitas: só 4, 8 e 16; o resto → `InvalidBracketError` (422) | SPEC 6.2: sem byes, então fora de escopo. |
| 2.17 | Adicionado o `pytest-cov`, com a cobertura de `app/` sempre exibida no `pytest` (`addopts`) | O SPEC pede cobertura alta no domínio. Resultado: **100% em `app/domain`**. Mostrar sempre torna as regressões visíveis, sem impor um mínimo (o SPEC diz para não perseguir cobertura nos routers). |
| 2.18 | Teste de "torneio inteiro" (o seed mais alto sempre vence → final é 1 vs 2) | Valida a geração, as ligações e o avanço juntos, de ponta a ponta, sem I/O. |

---

## Fase 3 — Persistência e API

### Mudanças

| # | O quê | Por quê |
|---|---|---|
| 3.1 | Dependências novas: `sqlalchemy[asyncio]` 2.1, `asyncpg` e `alembic` | É a stack definida no SPEC (seção 2). |
| 3.2 | `app/db.py`: uma sessão por requisição (dependency `get_session`), `expire_on_commit=False` | Com `expire_on_commit=False`, os objetos continuam legíveis depois do commit. Sem isso, o SQLAlchemy tentaria recarregá-los com I/O implícito, o que quebra em código async. |
| 3.3 | UUID gerado no Python (`uuid4`) **e** `server_default gen_random_uuid()` no banco | No Python, porque ao criar o chaveamento cada partida precisa do id da próxima (`next_match_id`) antes do insert. O default no banco atende o SPEC (seção 5) e cobre inserts feitos via SQL direto. |
| 3.4 | `created_at`/`updated_at` preenchidos no Python, com `now()` como default no banco | Valores definidos no servidor seriam "expirados" após o flush e exigiriam um reload implícito, de novo um problema em async. |
| 3.5 | Status em coluna `text` com `CHECK` em vez de `ENUM` nativo do Postgres | Adicionar valor a um ENUM nativo exige uma migration chata. Um `CHECK` se troca com um `ALTER` simples. A validação no banco é a mesma. |
| 3.6 | `naming_convention` no `MetaData` | Constraints e índices ganham nomes previsíveis (`fk_matches_team_a_id_teams`…), o que deixa as migrations futuras determinísticas. |
| 3.7 | **Colunas extras em `tournaments`: `rounds` e `version`** (não estão na seção 5 do SPEC) | O documento do torneio no Firestore (SPEC 8.1) tem `rounds` e `version`, e o write condicional (8.2) precisa da versão para ordenar as atualizações do torneio também. Guardar `rounds` evita recalcular a partir da contagem de times. |
| 3.8 | `outbox_events.id` como `BIGINT GENERATED BY DEFAULT AS IDENTITY` | É o equivalente moderno do `bigserial` pedido no SPEC (o mesmo tipo, a forma recomendada pelo Postgres). |
| 3.9 | Índice parcial `ix_outbox_events_pending ON (id) WHERE published_at IS NULL` | Exigido no SPEC. O relay só lê os pendentes, então o índice fica pequeno mesmo com milhões de eventos publicados. |
| 3.10 | Alembic com o template async. A URL vem das settings (`DATABASE_URL`), **não** do `alembic.ini`. Migration com id legível `0001` | O `alembic.ini` vai para o repo e não deve ter credenciais. Nos testes, a URL é injetada via `set_main_option`. O `alembic check` confirma que os models e a migration estão sincronizados. Também testei upgrade → downgrade → upgrade. |
| 3.11 | `config.attributes["configure_logger"]` no `env.py` | Quando os testes rodam a migration, o `fileConfig` do Alembic reconfiguraria o logging do pytest inteiro. A flag pula essa etapa. |
| 3.12 | Novas exceções: `VersionConflictError` (409, com `current_version` e `expected_version` em `details`), `NotFoundError` (404), `UnauthorizedError` (401) e `IdempotencyKeyReusedError` (422). Handlers para elas, para erros de validação do FastAPI e para `HTTPException` (404 de rota, 405) | **Todo** erro sai no formato `{"error": {"code", "message", "details"}}` do SPEC, inclusive os gerados pelo próprio FastAPI. Erro de validação e JSON malformado → 422 `validation_error`. |
| 3.13 | Auth com `APIKeyHeader(auto_error=False)` + `hmac.compare_digest` | A comparação em tempo constante é exigida no SPEC. Com `auto_error=False`, o 401 sai no nosso formato de erro. O `APIKeyHeader` também gera o botão "Authorize" no `/docs`. A dependency do `X-Internal-Token` já foi criada (será usada na Fase 4). |
| 3.14 | `Settings` guardado em `app.state.settings` e `create_app(settings)` aceitando settings injetadas | Os testes criam o app com um banco e chaves próprias, sem mexer em variáveis de ambiente nem no cache global. |
| 3.15 | **Os serviços retornam os modelos de resposta (Pydantic), montados dentro da sessão** | O SPEC fala em "objetos de domínio". Retornar linhas do ORM levaria a lazy-loading fora da sessão (que falha em async), e criar uma terceira camada de dataclasses duplicaria os schemas sem ganho. Os routers continuam sem lógica nenhuma. |
| 3.16 | A transação é aberta por `execute_write` (`app/services/idempotency.py`), que recebe a operação do serviço como uma função | Assim os routers não abrem transações (SPEC 10), e a idempotência fica **na mesma transação** da escrita. Os serviços documentam "chame dentro de uma transação". |
| 3.17 | Idempotência: `pg_advisory_xact_lock(hashtext(key))` + busca da chave + escrita + gravação da resposta, tudo numa transação | O lock serializa retries simultâneos com a mesma chave (há teste com 3 requisições em paralelo → 1 ponto aplicado). Como a resposta é salva junto com a escrita, não existe janela em que o ponto foi aplicado mas a resposta não foi salva. |
| 3.18 | Idempotência: só respostas de sucesso são guardadas | Se a escrita falha, a transação inteira é revertida, e o retry executa de novo, o que é o comportamento esperado (ex.: um 409 transitório). |
| 3.19 | Hash da requisição = método + path + JSON canônico (chaves ordenadas). Chave global (PK). Header `Idempotent-Replayed: true` nas respostas reaproveitadas | O JSON canônico evita falso "422 key reused" por diferença de espaços ou ordem das chaves. Incluir o path faz a mesma chave em endpoints diferentes dar 422. O header ajuda a depurar e não custa nada. |
| 3.20 | O `PUT /games/{index}` não aceita `Idempotency-Key` | O SPEC pede a chave só nos POST. O PUT já é naturalmente seguro: um retry com o mesmo `expected_version` dá 409, nunca uma aplicação dupla. |
| 3.21 | Lock: lê o `next_match_id` (imutável) e depois trava a partida e a próxima com `SELECT ... WHERE id IN (...) ORDER BY id FOR UPDATE`. O torneio é sempre travado **depois** das partidas | É a ordem determinística exigida no SPEC (seção 10), o que evita deadlock. As duas linhas são travadas já no início porque o ponto pode encerrar a partida e precisar mexer na próxima. `populate_existing` garante que os dados lidos são os do momento do lock. |
| 3.22 | A versão é checada **antes** do estado da partida | O cliente com versão velha recebe `version_conflict` com a `current_version` e sabe que precisa rebuscar. Um `invalid_state` vindo de dados velhos seria enganoso. |
| 3.23 | `POST /start` sem body e sem `expected_version` | O SPEC não define body para o start. A própria transição já protege: o segundo start dá 409 `invalid_state`. |
| 3.24 | O start abre o primeiro game em 0-0 e, se o torneio está `scheduled`, muda para `in_progress` (+ evento `tournament_updated`) | O espectador vê o 0-0 assim que a partida começa. O SPEC tem o status `in_progress` mas não diz quando entrar nele: a escolha mais natural é a primeira partida começar. |
| 3.25 | Correções só em partidas `live`. Uma correção que decide a partida dispara o mesmo fluxo de término e avanço | Corrigir uma partida já finalizada exigiria "desfazer" o avanço no chaveamento, o que está fora do escopo. A correção que encerra a partida reaproveita o código do ponto final (um caminho só). |
| 3.26 | Ao criar o torneio, são gravados no outbox um `tournament_updated` e um `match_updated` **para cada partida** | Assim o read model no Firestore recebe o chaveamento vazio inteiro desde o início, e os clientes conseguem desenhar a árvore antes da primeira partida. |
| 3.27 | Inserts em ordem explícita, com `flush` entre eles (torneio → times → partidas da final para a 1ª rodada) | Não há `relationship()` no ORM (de propósito, para evitar lazy-loading), então o SQLAlchemy não sabe a ordem das FKs. Uma partida referencia a próxima, por isso as rodadas posteriores entram primeiro. |
| 3.28 | Os times são semeados pela ordem da lista (o primeiro é o seed 1) | É a API mais simples. Seeds explícitos exigiriam validar duplicatas e lacunas sem nenhum benefício para a demo. |
| 3.29 | **`projector.py` criado já na Fase 3** (o SPEC o coloca na Fase 4) | O payload do outbox é o documento já projetado (SPEC 8.1), e é gravado na mesma transação da escrita. Sem o projector, não daria para gravar o outbox corretamente na Fase 3. |
| 3.30 | Escrita do outbox em `app/outbox/events.py` (arquivo não listado no SPEC) e `EventType` como `StrEnum` | Separa "gravar evento" (Fase 3) de "publicar evento" (`relay.py`, Fase 4). O enum evita erro de digitação nos nomes dos eventos. |
| 3.31 | `app/routers/responses.py`: os erros 401/404/409/422 documentados no OpenAPI e o helper `write_response` | O `/docs` mostra o formato de erro em cada endpoint (o SPEC pede um `/docs` apresentável). As escritas devolvem `JSONResponse`, porque a resposta reaproveitada já está em JSON. |
| 3.32 | `GET /health/ready` faz `SELECT 1` e responde 503 se o banco não responder | É o probe de readiness do SPEC (seção 7). O 503 é o padrão que load balancers e o Cloud Run entendem. |
| 3.33 | Testes de integração num banco separado, `scores_test`, criado automaticamente, migrado **pelo Alembic** e com `TRUNCATE` antes de cada teste | Rodar os testes não apaga os dados de dev. Usar o Alembic em vez de `create_all` testa a própria migration. O `TRUNCATE` deixa cada teste independente. A URL pode ser trocada via `TEST_DATABASE_URL`. |
| 3.34 | Nenhum fake de Firestore na Fase 3 | Nada publica no Firestore ainda (o relay é da Fase 4). Os testes verificam as linhas do outbox diretamente, o que é mais preciso. |
| 3.35 | `[tool.coverage.run] concurrency = ["greenlet", "thread"]` | O SQLAlchemy async executa o código dentro de greenlets, e sem essa opção o coverage mostrava 45% em `services/matches.py` mesmo com tudo testado. Agora a cobertura reflete a realidade (98% no geral). |
| 3.36 | O Dockerfile volta a copiar `migrations/` e `alembic.ini`. A CI ganhou o Postgres 16 como service container e um passo `make migrate` | A imagem precisa das migrations para o Cloud Run Job (SPEC 16). A CI passa a rodar os testes de integração. |

---

## Fase 4 — Read model em tempo real

### Mudanças

| # | O quê | Por quê |
|---|---|---|
| 4.1 | Dependências novas: `google-cloud-firestore` (2.34, `AsyncClient`) e `firebase-admin` (7.7) | É a stack do SPEC (seção 2). |
| 4.2 | **Campo `tournamentId` adicionado ao documento da partida** (não está no exemplo da seção 8.1) | O relay só conhece o `aggregate_id` da partida, e o caminho do documento (`tournaments/{tournamentId}/matches/{matchId}`) exige o torneio. As alternativas eram uma coluna extra no outbox ou um JOIN no `SELECT ... FOR UPDATE SKIP LOCKED` (que travaria também as partidas). O campo também ajuda o cliente Flutter em consultas `collectionGroup`. |
| 4.3 | Publisher com **transação do Firestore**: lê o documento; se `armazenado.version >= nova.version`, pula e retorna `False`; senão grava o payload + `updatedAt = SERVER_TIMESTAMP` | É exatamente o SPEC 8.2. A publicação fica idempotente e segura contra ordem trocada (teste: grava v5, tenta v4 e v5 de novo → fica a v5). |
| 4.4 | `Publisher` e `Notifier` como `Protocol` | Os testes usam implementações falsas (`FailingPublisher`, `RecordingNotifier`) sem mock nem monkeypatch, e o mypy verifica a compatibilidade. |
| 4.5 | `create_firestore_client` copia o `FIRESTORE_EMULATOR_HOST` das settings para `os.environ` | A biblioteca do Google só detecta o emulador pela variável de ambiente do processo, e o `pydantic-settings` lê o `.env` sem exportar nada para o ambiente. Em prod a variável não existe, e o client usa as credenciais padrão (ADC) da service account do Cloud Run. |
| 4.6 | Agrupamento (`coalesce`) é uma função pura: agrupa por `(aggregate_type, aggregate_id)` e escolhe a maior `aggregate_version` | O SPEC 9.2 pede isso, e o SPEC 14 pede o teste unitário da função pura. A escolha é pela versão, não pelo id do evento, para não depender da ordem de inserção. |
| 4.7 | **Os eventos antigos do grupo só são marcados como publicados se o mais novo for publicado com sucesso.** Se falhar, o grupo todo continua pendente, e `attempts`/`last_error` sobem só no evento mais novo | O SPEC diz que os antigos "são marcados como publicados (foram substituídos)". Mas, se o mais novo falhar, o próximo drain precisa dos antigos para não perder as notificações (ex.: um `match_started` que foi agrupado com pontos). O resultado no Firestore é o mesmo. |
| 4.8 | Notificações vêm de **todos** os `match_started`/`match_finished` do grupo, não só do evento publicado | Com o agrupamento, um `match_started` costuma ser "engolido" pelos pontos seguintes no mesmo lote. Se só o evento publicado notificasse, o push "partida começou" se perderia (há teste para isso). |
| 4.9 | Notificações são enviadas **depois do commit** do drain. Falha de notificação é só logada | É o SPEC 9.5. Depois do commit, um crash no meio não gera notificações para eventos que voltariam a ficar pendentes. A garantia é "pelo menos uma vez": em casos raros, um push pode chegar duplicado. |
| 4.10 | O drain é uma transação única: `SELECT ... FOR UPDATE SKIP LOCKED` → publica (no máximo 20 em paralelo, via `Semaphore`) → marca → commit. Cada publicação tem timeout de 10s | Os locks impedem que dois drains simultâneos (o caminho rápido de várias requisições + o Scheduler) publiquem os mesmos eventos. O timeout limita quanto tempo os locks e a conexão ficam presos se o Firestore estiver lento. |
| 4.11 | `DrainResult`: `published` = eventos marcados como publicados (inclusive os substituídos), `failed` = eventos cuja publicação falhou (um por agregado), `remaining` = pendentes após o drain | O SPEC define os campos mas não a contagem exata. Esta é a interpretação mais útil para monitorar o backlog. |
| 4.12 | **Caminho rápido:** cada escrita bem-sucedida devolve a resposta com um `BackgroundTask(relay.drain_safely)` | O Starlette roda a tarefa depois de enviar a resposta, ou seja, depois do commit (SPEC 9). O `drain_safely` nunca lança exceção, só loga. Respostas reaproveitadas de idempotência não disparam drain (não houve escrita nova). |
| 4.13 | O `POST /internal/outbox/drain` chama `drain_until_empty` (até 10 lotes, para no primeiro lote com falha) | Se um backlog grande se acumular (ex.: Firestore fora do ar), uma chamada por minuto do Scheduler com um lote só demoraria muito para zerar. Parar ao primeiro erro evita martelar um Firestore que está falhando. |
| 4.14 | O relay é criado no `lifespan` (`app.state.relay`). `create_app` aceita `publisher`/`notifier` para testes | É uma instância por processo, que reaproveita o client do Firestore (conexão gRPC). A injeção evita monkeypatch nos testes. |
| 4.15 | `python -m app.outbox`: loop de `drain()` a cada 500 ms, sai limpo no Ctrl+C e fecha o engine e o client | É o SPEC 9 (dev). Um erro em um ciclo é logado e o loop continua, porque uma falha transitória não deve derrubar o relay. |
| 4.16 | **Sem loop em background dentro do serviço do Cloud Run** | No Cloud Run com CPU alocada só durante as requisições, a CPU fica estrangulada entre elas, e um loop de background não roda de forma confiável. A rede de segurança é o Cloud Scheduler chamando o endpoint de drain a cada minuto. As alternativas seriam CPU sempre alocada (mais cara) ou um worker separado (mais infraestrutura). Ficamos com o mais simples. |
| 4.17 | `FcmNotifier` (Admin SDK, tópico `tournament_{id}`) atrás de `FCM_ENABLED`. `LoggingNotifier` em dev. O SDK roda em `asyncio.to_thread` | O SDK do Firebase Admin é síncrono e bloquearia o event loop. Ele usa ADC, então não há arquivo de chave (SPEC regra 4). O `firebase_admin` é importado só quando o FCM está ligado, então dev e testes não dependem dele. |
| 4.18 | Override do mypy `ignore_missing_imports` para `firebase_admin`, e um `type: ignore[no-untyped-call]` comentado no `close()` do Firestore | As duas bibliotecas de terceiros não têm tipos nesses pontos. O `--strict` continua valendo para todo o nosso código. |
| 4.19 | **O emulador trocou de `gcloud` para o Firebase CLI** (imagem própria em `docker/firebase-emulator/`: Node 24 + JDK 21 + `firebase-tools@15.33.0`) | O emulador do `gcloud` não tem interface, e o aceite da Fase 5 é **ver os documentos mudando na UI do emulador** (Emulator Suite UI, `http://localhost:4000`). O Firebase CLI também carrega o `firestore.rules` automaticamente, então o comportamento local é igual ao de produção. O SPEC citava o `gcloud` só como exemplo ("ex.:"). |
| 4.20 | `firebase.json` e `firestore.rules` montados como volume no compose (não copiados para a imagem) | Editar as rules vale com um `docker compose restart firestore`, sem rebuild. A imagem contém só as ferramentas. |
| 4.21 | Healthcheck no emulador (`curl` na porta 8081), e o serviço `api` passou a esperar `service_healthy` | O `make up` (com `--wait`) só retorna quando o emulador realmente aceita conexões, o que evita testes falhando por corrida na CI. |
| 4.22 | `firestore.rules`: leitura pública em `tournaments/**`, nenhuma escrita de cliente, todo o resto fechado | É o SPEC 8.3. O Admin SDK ignora as rules, então só o backend escreve. O comentário no arquivo registra que em produção a leitura poderia exigir Firebase Auth ou App Check. |
| 4.23 | **Teste das rules em Python**, carregando o `firestore.rules` no emulador via REST (`PUT /emulator/v1/projects/{p}:securityRules`) e fazendo leituras e escritas anônimas | O SPEC pede o teste "se for simples". Com REST puro ficou simples, sem Node nem `@firebase/rules-unit-testing`. O teste usa o arquivo atual (não o que o container carregou) num projeto próprio. |
| 4.24 | Testes de integração usam o projeto `demo-live-scores-test` no emulador, limpo antes de cada teste (`DELETE .../documents`) | Isola os testes dos dados de dev (o projeto `demo-live-scores`). O prefixo `demo-` faz o Firebase tratar como projeto fictício, sem nada real. |
| 4.25 | A CI usa `make up` (o mesmo compose do dev) em vez do service container, e mostra os logs dos containers quando falha | O emulador precisa de comando e build próprios, que service containers do GitHub não suportam. Usar o mesmo compose garante que CI e dev rodam igual. |
| 4.26 | Teste de ponta a ponta manual (não automatizado): a API com o emulador inacessível → `failed=4, remaining=4`, e depois o `python -m app.outbox` → `published=4`, com os documentos no Firestore | Confirma o fluxo de falha + retry com processos reais, que é exatamente o cenário de produção do SPEC 3 (passo 5). |
| 4.27 | `.env` criado localmente a partir do `.env.example` (ele está no `.gitignore`) | Sem ele, `FIRESTORE_EMULATOR_HOST` não fica definido no dev, e o client tentaria o Firestore real. O README da Fase 5 vai incluir `cp .env.example .env`. |
| 4.28 | `.gitattributes` com `* text=auto eol=lf` (adicionado no commit inicial) | Nesta máquina o Git usa `core.autocrlf=true`, que converteria os arquivos para CRLF no checkout. Makefile, Dockerfiles e comandos de shell executados dentro de containers Linux quebram com CRLF. Fixar LF deixa o repositório igual em Windows, Linux e CI. |

---

## Commit inicial

Feito a pedido do dono do repositório depois da aprovação da Fase 4: commit `ffb3074` na branch
`main`, com as Fases 1 a 4 e uma mensagem descrevendo cada fase. O `.env` e o `.venv` ficaram de
fora (`.gitignore`), e verifiquei que nenhum arquivo de credencial entrou.

---

## Fase 5 — Demo e docs

### Mudanças

| # | O quê | Por quê |
|---|---|---|
| 5.1 | `scripts/seed.py` cria o "Demo Open" (8 times com nomes temáticos) **pela API** e imprime o id, o link do bracket, o link direto da UI do emulador e o comando do simulador | É o pedido do SPEC 13. Imprimir o próximo comando pronto para copiar reduz o atrito do "Run it in 5 minutes". |
| 5.2 | `scripts/simulate.py` joga rodada por rodada; as partidas da mesma rodada jogam em paralelo (`asyncio.gather`); `--speed` = pontos por segundo por partida | É o SPEC 13. O bracket é relido a cada rodada, porque os vencedores da anterior só estão definidos depois dela. |
| 5.3 | Em `409 version_conflict`, o simulador usa a `details.current_version` do erro e tenta de novo, sem buscar o bracket inteiro | O SPEC diz "rebusca e tenta de novo". A `current_version` que a API devolve é exatamente o que precisa ser rebuscado, e não existe `GET /matches/{id}` (criar um seria funcionalidade fora do escopo). |
| 5.4 | O simulador manda `Idempotency-Key` em todo POST e repete falhas de rede **com a mesma chave** (backoff exponencial, 5 tentativas) | Demonstra o uso correto da idempotência: um timeout após o commit não aplica o ponto duas vezes. |
| 5.5 | O simulador retoma um torneio pela metade: partidas `live` continuam, as `finished` são puladas | Se a demo for interrompida (Ctrl+C), basta rodar de novo. Isso foi testado de verdade nesta fase. |
| 5.6 | Pequena vantagem para o melhor seed (probabilidade de ponto entre 35% e 65%) | Os resultados ficam plausíveis (favoritos costumam avançar) sem eliminar as zebras. |
| 5.7 | Log compacto: uma linha por início de partida, fim de game e resultado final, com tempo decorrido. `--verbose` mostra cada ponto | O SPEC pede um "log compacto". Com 4 partidas a 5 pontos/s, logar cada ponto daria 20 linhas por segundo. |
| 5.8 | Os scripts também passam no `mypy --strict`, e o `make lint` agora os verifica | O SPEC exige strict só em `app/`, mas os scripts são código de demo que recrutadores vão ler. Custou uma linha no Makefile. |
| 5.9 | **`migrations/env.py` lê o `DATABASE_URL` direto do ambiente antes de carregar as `Settings`** | Bug encontrado ao escrever o DEPLOY.md. A imagem roda com `ENV=prod`, e carregar as `Settings` em prod exige `API_KEY` e `INTERNAL_TOKEN`. O Cloud Run Job de migration falharia sem segredos de que não precisa. Testado com a imagem de produção contra um banco novo. |
| 5.10 | README com as 10 seções do SPEC 17, em inglês, tom de decisão de engenharia. O placeholder do GIF fica no topo | Conteúdo obrigatório do SPEC. O GIF será gravado pelo dono do repositório (Fase 6). |
| 5.11 | "Run it in 5 minutes" testado do zero: `docker compose down -v` → up → migrate → run + relay → seed → simulate | É o aceite da Fase 5. Resultado: torneio `finished`, as 7 partidas `finished` no Firestore com as versões iguais às do Postgres, 302 eventos no outbox e 0 pendentes. O `make up` levou 7s com a imagem já construída; o primeiro build do emulador leva alguns minutos, e o README avisa isso. |
| 5.12 | `docs/SCALING.md` com a **fórmula de custo escrita** (`R = V × ((1 + M) + M × U + T)`), as hipóteses (`U ≈ 50` pontos por partida) e uma tabela de cenários com faixa de preço | O SPEC pede a fórmula, não só o número, e a ressalva de que o preço varia por região. Usei uma faixa ($0.03–$0.06 por 100k leituras) em vez de um valor exato. |
| 5.13 | A principal alavanca de escala descrita é um **documento de resumo** atualizado só em mudanças estruturais (~5 por partida), com listeners por partida apenas nas partidas que o usuário está vendo | É a sugestão do SPEC, detalhada com a conta: 2–3× menos leituras para 8 times, e mais para chaveamentos maiores. O agrupamento em janelas de 1–2s aparece como segunda alavanca, porque no jogo real um ponto leva mais de 10s. |
| 5.14 | `docs/DEPLOY.md` com comandos `gcloud` passo a passo: Cloud SQL (socket via conector, `?host=/cloudsql/...` para o asyncpg), Firestore Native, service account **sem arquivo de chave**, Secret Manager, Job de migration, deploy, Cloud Scheduler e as rules | É o SPEC 16. Documentei também uma limitação: o token do Scheduler fica visível na configuração do job, e a alternativa mais estrita é o token OIDC. |
| 5.15 | Cloud Run com `--allow-unauthenticated` | As leituras são públicas, e as escritas são protegidas pela própria API (`X-API-Key`). Exigir IAM no Cloud Run bloquearia o app Flutter e o simulador. |
| 5.16 | Encerrei os processos locais da API e do relay usados na validação. Postgres e emulador continuam rodando no Docker | Para não deixar processos órfãos na máquina. Os containers ficam no ar porque são o ambiente de dev. |

---

## Commit da Fase 5

Commit `0024ae2`, a pedido do dono do repositório, antes de começar a Fase 6.

---

## Fase 6 — Visualizador Flutter

### Mudanças

| # | O quê | Por quê |
|---|---|---|
| 6.1 | `client_flutter/` criado com `flutter create` (Flutter 3.47.3 / Dart 3.13), para Android, iOS e **web** | A web permite ver o app no Chrome sem emulador Android/iOS: é o caminho mais rápido para a demo e para gravar o GIF. Desktop ficou de fora porque o suporte do `cloud_firestore` a desktop é limitado. |
| 6.2 | Dependências só `firebase_core` e `cloud_firestore`, sem gerenciamento de estado | O SPEC pede "`StreamBuilder` basta". O app não tem estado próprio: tudo vem dos snapshots. |
| 6.3 | `FirebaseOptions` fictícias em `lib/config.dart` em vez de `flutterfire configure` | O emulador ignora credenciais. Gerar `firebase_options.dart` exigiria um projeto Firebase real e colocaria ids no repositório. O README do app explica como trocar para um projeto real. |
| 6.4 | Configuração via `--dart-define` (`FIRESTORE_EMULATOR_HOST`, `FIRESTORE_EMULATOR_PORT`, `FIREBASE_PROJECT_ID`, `USE_FIRESTORE_EMULATOR`). Host padrão `10.0.2.2` no Android e `localhost` no resto | O emulador Android acessa o host por `10.0.2.2`. Um dispositivo físico precisa do IP da máquina na rede. Os defaults fazem o caso comum funcionar sem nenhum parâmetro. |
| 6.5 | Tela inicial lista os torneios (`tournaments` ordenados por `updatedAt`), e o toque abre o chaveamento | O SPEC não diz como o app descobre o torneio. A lista evita digitar ou colar o id e funciona com qualquer `make seed`. |
| 6.6 | Chaveamento com **dois listeners**: o documento do torneio (nome e status) e a subcoleção `matches` | É exatamente o modelo de leitura desenhado no backend: um documento por partida. |
| 6.7 | Layout responsivo: em telas largas (≥ 720px), uma coluna por rodada lado a lado; em celular, uma aba por rodada | Colunas lado a lado parecem um chaveamento de verdade no desktop/web, mas ficariam ilegíveis no celular. |
| 6.8 | **Destaque ao mudar o placar:** o card pisca (cor `tertiaryContainer` → normal em 900ms) quando chega uma versão **maior** com games ou status diferentes. Os números trocam com `AnimatedSwitcher` (escala) | É o pedido do SPEC ("destaque visual rápido"). Comparar a `version` evita piscar quando um snapshot repetido chega (ex.: reconexão), e há teste para isso. |
| 6.9 | O game em andamento aparece em negrito na cor primária; o vencedor em negrito; o perdedor e o "TBD" em cinza | Dá para ler a partida de relance, sem legenda. |
| 6.10 | Parsing dos documentos em `lib/models.dart`, puro e tolerante (números aceitos como `int` ou `double`, campos ausentes com default) | É testável sem Firebase. A tolerância evita crash se um documento vier incompleto ou com números serializados como `double` (acontece na web). |
| 6.11 | 11 testes: parsing, nomes das rodadas, agrupamento, renderização do card e o destaque (pisca numa versão nova, não pisca numa repetida). O `widget_test.dart` padrão foi removido | Cobre a lógica e o comportamento visual pedido sem precisar de Firestore, nem real nem fake. |
| 6.12 | Android: `usesCleartextTraffic="true"` **só no manifest de debug**, e a permissão `INTERNET` adicionada ao manifest principal | O emulador do Firestore usa HTTP sem TLS, e o Android bloqueia tráfego em texto puro por padrão. Liberar só no debug não afeta builds de release. Sem `INTERNET` no manifest principal, um build de release nem conseguiria acessar o Firestore real. |
| 6.13 | Compilação validada com `flutter build web` e `flutter build apk --debug`, **sem rodar nenhum emulador** | A pedido do dono do repositório, o emulador não foi iniciado. Os dois builds passaram e garantem que o código compila nas plataformas alvo. O build Android mostra avisos de depreciação (Kotlin/Gradle e operações *unchecked*) vindos do plugin `cloud_firestore` 6.10, não do nosso código. Eles somem quando o plugin for atualizado. O app **ainda não foi executado** contra o emulador do Firestore. |
| 6.14 | `make viewer` (`flutter run -d chrome`) e um job `flutter-viewer` na CI (format, analyze, test) | Um comando para a demo e a garantia de que o app não quebra em PRs. O job é separado para não deixar o pipeline do backend mais lento. |
| 6.15 | O placeholder do GIF no README virou um comentário com o caminho esperado (`docs/demo.gif`) | Um link de imagem quebrado no README ficaria feio para recrutadores. O comentário diz exatamente o que fazer depois de gravar. |

---

## Publicação no GitHub

| # | O quê | Por quê |
|---|---|---|
| 7.1 | O repositório `victorlamarck/PlayPickleball` foi criado com um commit inicial (`README.md` de uma linha). O dono do repositório fez o merge com `--allow-unrelated-histories` (commit `ede4e31`), mantendo o README completo, e o push | Junta os dois históricos sem `push --force`. Os commits das fases são preservados. |
| 7.2 | Badge de CI apontando para `victorlamarck/PlayPickleball` | Substitui o placeholder `OWNER/REPO` agora que o repositório existe. |

