# Deploying to Cloud Run

A manual deployment, step by step. CI does not deploy. Commands assume `gcloud` is authenticated
(`gcloud auth login`) and use bash syntax.

```bash
export PROJECT_ID=my-project
export REGION=us-central1
export SERVICE=live-scores-api
export REPO=live-scores
export SQL_INSTANCE=live-scores-pg
export SA=live-scores-api@${PROJECT_ID}.iam.gserviceaccount.com
export IMAGE=${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/api:$(git rev-parse --short HEAD)

gcloud config set project "$PROJECT_ID"
```

## 1. Enable the APIs

```bash
gcloud services enable run.googleapis.com sqladmin.googleapis.com firestore.googleapis.com \
  secretmanager.googleapis.com cloudscheduler.googleapis.com artifactregistry.googleapis.com \
  cloudbuild.googleapis.com
```

## 2. Postgres (Cloud SQL)

```bash
gcloud sql instances create "$SQL_INSTANCE" --database-version=POSTGRES_16 \
  --region="$REGION" --tier=db-g1-small --storage-auto-increase
gcloud sql databases create scores --instance="$SQL_INSTANCE"
gcloud sql users create scores --instance="$SQL_INSTANCE" --password="$(openssl rand -hex 24)"
# Write the password down for DATABASE_URL below (or reset it with `gcloud sql users set-password`).
```

Cloud Run connects through the Cloud SQL connector, which exposes a Unix socket
(`--add-cloudsql-instances`). asyncpg takes the socket directory as `host`:

```
postgresql+asyncpg://scores:<password>@/scores?host=/cloudsql/<PROJECT_ID>:<REGION>:<SQL_INSTANCE>
```

Any other Postgres 16 works too, over a public URL with TLS:
`postgresql+asyncpg://user:pass@host:5432/scores?ssl=require`.

## 3. Firestore (Native mode)

```bash
gcloud firestore databases create --location="$REGION" --type=firestore-native
```

## 4. Service account (no key files)

The service runs as this identity; the Google client libraries pick it up through Application
Default Credentials. No JSON key is created or stored anywhere.

```bash
gcloud iam service-accounts create live-scores-api --display-name="Live scores API"
for role in roles/datastore.user roles/cloudsql.client roles/secretmanager.secretAccessor; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$SA" --role="$role"
done
# Only if FCM_ENABLED=true:
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$SA" \
  --role=roles/firebasemessaging.admin
```

For tighter scoping, grant `secretAccessor` on each secret instead of on the project.

## 5. Secrets (Secret Manager)

```bash
printf '%s' "$(openssl rand -hex 32)" | gcloud secrets create API_KEY --data-file=-
printf '%s' "$(openssl rand -hex 32)" | gcloud secrets create INTERNAL_TOKEN --data-file=-
printf '%s' 'postgresql+asyncpg://scores:<password>@/scores?host=/cloudsql/'"$PROJECT_ID:$REGION:$SQL_INSTANCE" \
  | gcloud secrets create DATABASE_URL --data-file=-
```

The app refuses to start in `ENV=prod` with the dev defaults for `API_KEY` or `INTERNAL_TOKEN`.

## 6. Build the image

```bash
gcloud artifacts repositories create "$REPO" --repository-format=docker --location="$REGION"
gcloud builds submit --tag "$IMAGE"
```

## 7. Run migrations (Cloud Run Job), before every deploy

Migrations run as a one-off job from the same image. They need only `DATABASE_URL`.

```bash
gcloud run jobs create live-scores-migrate --image="$IMAGE" --region="$REGION" \
  --service-account="$SA" --set-cloudsql-instances="$PROJECT_ID:$REGION:$SQL_INSTANCE" \
  --set-secrets=DATABASE_URL=DATABASE_URL:latest \
  --command=alembic --args=upgrade,head

gcloud run jobs execute live-scores-migrate --region="$REGION" --wait
```

On later deploys, point the job at the new image first:
`gcloud run jobs update live-scores-migrate --image="$IMAGE" --region="$REGION"`.

## 8. Deploy the service

```bash
gcloud run deploy "$SERVICE" --image="$IMAGE" --region="$REGION" \
  --service-account="$SA" --add-cloudsql-instances="$PROJECT_ID:$REGION:$SQL_INSTANCE" \
  --set-secrets=API_KEY=API_KEY:latest,INTERNAL_TOKEN=INTERNAL_TOKEN:latest,DATABASE_URL=DATABASE_URL:latest \
  --set-env-vars=ENV=prod,GCP_PROJECT_ID="$PROJECT_ID",FCM_ENABLED=false,LOG_LEVEL=INFO \
  --allow-unauthenticated

export SERVICE_URL=$(gcloud run services describe "$SERVICE" --region="$REGION" --format='value(status.url)')
curl "$SERVICE_URL/health/ready"
```

`--allow-unauthenticated` is intentional: reads are public and writes are protected by the API's
own `X-API-Key` check. Do **not** set `FIRESTORE_EMULATOR_HOST` in production.

The default CPU allocation ("CPU only during requests") is fine. The post-commit drain runs in
the request's background task, and the scheduler below is the safety net. There is no background
loop in the service (see `docs/DECISIONS.md`, item 4.16).

## 9. Outbox safety net (Cloud Scheduler)

```bash
gcloud scheduler jobs create http outbox-drain --location="$REGION" \
  --schedule="* * * * *" --http-method=POST \
  --uri="$SERVICE_URL/internal/outbox/drain" \
  --headers="X-Internal-Token=$(gcloud secrets versions access latest --secret=INTERNAL_TOKEN)"
```

The token is stored in the scheduler job's configuration and is visible to anyone who can read
scheduler jobs. A stricter setup would use an OIDC token from Cloud Scheduler, checked by the app
or by a separate private Cloud Run service for internal endpoints.

## 10. Firestore security rules

```bash
npx firebase-tools deploy --only firestore:rules --project "$PROJECT_ID"
```

The rules allow public reads under `tournaments/**` and deny every client write. The backend
writes with its service account, which is not subject to rules.

## Every deploy, in short

```bash
gcloud builds submit --tag "$IMAGE"
gcloud run jobs update live-scores-migrate --image="$IMAGE" --region="$REGION"
gcloud run jobs execute live-scores-migrate --region="$REGION" --wait
gcloud run deploy "$SERVICE" --image="$IMAGE" --region="$REGION"
```
