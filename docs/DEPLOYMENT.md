# Deployment Guide — Healthcare Copilot

Covers single-VM (pilot) and managed/scaled (production) deployments on AWS and
Azure, VM sizing, cost estimates, scaling, and the go-live checklist.

> ⚠️ **PHI / HIPAA:** this app stores PHI. On AWS use a **HIPAA-eligible** account
> with a signed BAA; on Azure ensure your subscription is covered by the Microsoft
> BAA. Encrypt all volumes, enable audit logging, and restrict network access.

---

## 0. Topology

```
            (TLS)                         (private network)
Internet ──▶ Load Balancer / nginx ──▶ frontend (nginx: SPA + proxy)
                                          │  /api,/ws
                                          ▼
                                        backend (uvicorn x4, --proxy-headers)
                                          ├── PostgreSQL (primary + read replica)
                                          ├── Redis (sessions, cache, denylist)
                                          ├── ChromaDB (schema vectors)
                                          └── Neo4j (knowledge graph)
                              observability: Prometheus + Grafana + Jaeger
```
The backend runs **two DB identities**: the app role (writes) and `hc_readonly`
(executes AI-generated SQL, RLS-enforced). See `scripts/sql/create_readonly_role.sql`.

---

## 1. Minimum VM requirements

| Scenario | vCPU | RAM | Disk | Notes |
|---|---:|---:|---:|---|
| **Pilot / all-in-one** (1 VM, `docker-compose.prod.yml`) | 4 | 16 GB | 100 GB SSD | 4 uvicorn workers each load the embedding model (~0.5 GB) + Postgres/Redis/Neo4j/Chroma |
| Bare minimum (≤10 users, reduce workers to 2) | 2 | 8 GB | 50 GB SSD | Set `--workers 2`; expect slower cold starts |
| **Production backend node** (managed datastores) | 4 | 8 GB | 40 GB | Stateless; scale horizontally |
| PostgreSQL (managed) | 2 | 8 GB | 100 GB gp3 | Enable a read replica for `hc_readonly` |
| Redis (managed) | — | 1–2 GB | — | `cache.t4g.small` / Basic C1 |

LLM inference is **external** (Groq/OpenAI-compatible) — no GPU needed locally.
If self-hosting an LLM, add a separate GPU node (out of scope here).

---

## 2. Pilot deployment (single VM — fastest path)

Works identically on an AWS EC2 or Azure VM (Ubuntu 22.04).

```bash
# 1. Install Docker + compose plugin
curl -fsSL https://get.docker.com | sh

# 2. Clone and configure
git clone <repo> && cd healthcare-copilot
cp backend/.env.example .env
#   Edit .env — set STRONG values for:
#   APP_ENV=production  SECRET_KEY  JWT_SECRET_KEY
#   POSTGRES_PASSWORD  REDIS_PASSWORD  NEO4J_PASSWORD  GRAFANA_ADMIN_PASSWORD
#   LLM_API_KEY  CORS_ALLOWED_ORIGINS=https://your-domain
#   READONLY_POSTGRES_USER=hc_readonly  READONLY_POSTGRES_PASSWORD=...
#   PHI_ENCRYPTION_KEYS=$(docker run --rm python:3.11-slim sh -c "pip -q install cryptography && python -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())'")

# 3. Bring up the stack (runs migrations via the one-shot `migrate` service)
docker compose -f docker-compose.prod.yml up -d --build

# 4. One-time: provision the least-privilege read-only role
docker compose -f docker-compose.prod.yml exec -T postgres \
  psql -U hc_user -d healthcopilot -v ro_password="$READONLY_POSTGRES_PASSWORD" \
  < backend/scripts/sql/create_readonly_role.sql

# 5. Seed demo users (optional, non-prod)
docker compose -f docker-compose.prod.yml exec backend python -m app.scripts.seed_db
```

**TLS options:**
- **Cloud LB (recommended):** put an AWS ALB / Azure App Gateway in front of the
  `frontend` container (port 80) and attach an ACM / Key Vault cert. The backend
  already honors `X-Forwarded-Proto` (`--proxy-headers`).
- **Self-managed:** use `deploy/nginx/nginx-tls.conf`, mount Let's Encrypt certs,
  and publish `443:443` on the `frontend` service.

---

## 3. AWS deployment guide

### 3a. Quick (EC2 + Docker Compose)
1. Launch **t3.xlarge** (4 vCPU/16 GB), Ubuntu 22.04, 100 GB gp3 (encrypted).
2. Security group: inbound 443 (and 80 → redirect) from the internet; 22 from your IP only. **Do not** expose 5432/6379/7687/9090.
3. Route53 A-record → EC2 EIP. ACM cert on an ALB, or certbot on the box.
4. Store secrets in **AWS Secrets Manager**; inject into `.env` at boot (user-data).
5. Follow §2.

### 3b. Scalable (ECS Fargate + managed data)
| Component | AWS service |
|---|---|
| Backend / frontend images | ECR |
| Containers | ECS Fargate (backend service N tasks + frontend service) |
| Ingress + TLS | Application Load Balancer + ACM (HTTPS:443) |
| PostgreSQL | **RDS for PostgreSQL 16**, Multi-AZ, + **read replica** for `hc_readonly` |
| Redis | ElastiCache for Redis |
| Vectors | ChromaDB on a small ECS task with EFS, or swap to a managed vector DB |
| Secrets | Secrets Manager → ECS task `secrets` |
| Backups | RDS automated snapshots (PITR) + `scripts/backup` to S3 |
| Logs/metrics | CloudWatch + the bundled Prometheus/Grafana, or AMP/AMG |

- Run migrations as an ECS **one-off task** (`bash scripts/entrypoint.sh`) on deploy.
- Point `READONLY_POSTGRES_HOST` at the **RDS read-replica** endpoint.
- ALB target group health check → `/healthz` (frontend) and `/health` (backend).
- Autoscale the backend service on CPU/ALB request count.

---

## 4. Azure deployment guide

### 4a. Quick (VM + Docker Compose)
1. Create **Standard_D4s_v5** (4 vCPU/16 GB), Ubuntu 22.04, Premium SSD (encrypted).
2. NSG: allow 443/80 from internet, 22 from your IP; block datastore ports.
3. Public DNS / Azure DNS A-record. TLS via App Gateway/Front Door or certbot.
4. Secrets in **Azure Key Vault**; pull into `.env` at boot.
5. Follow §2.

### 4b. Scalable (Container Apps / AKS + managed data)
| Component | Azure service |
|---|---|
| Images | Azure Container Registry (ACR) |
| Containers | Azure Container Apps (backend + frontend) or AKS |
| Ingress + TLS | Application Gateway / Front Door + managed cert |
| PostgreSQL | **Azure Database for PostgreSQL Flexible Server 16** + read replica |
| Redis | Azure Cache for Redis |
| Vectors | ChromaDB container w/ Azure Files, or a managed vector DB |
| Secrets | Key Vault + Container Apps secret refs |
| Backups | Flexible Server PITR + `scripts/backup` to Blob Storage |
| Observability | Azure Monitor / Managed Grafana |

- Migrations: Container Apps **job** running `bash scripts/entrypoint.sh` pre-deploy.
- `READONLY_POSTGRES_HOST` → PostgreSQL read replica.

---

## 5. Expected costs (rough, USD/month, on-demand, excl. data egress & LLM usage)

| Tier | AWS | Azure |
|---|---|---|
| **Pilot** (1 VM all-in-one) | t3.xlarge ~$120 + 100 GB gp3 ~$8 ≈ **$130** | D4s_v5 ~$140 + disk ~$10 ≈ **$150** |
| **Production (managed, small)** | Fargate 2×(1vCPU/2GB) ~$70 + RDS db.t4g.large Multi-AZ ~$250 + replica ~$120 + ElastiCache t4g.small ~$25 + ALB ~$20 ≈ **$485** | Container Apps ~$80 + PostgreSQL Flexible D2ds Zone-redundant ~$280 + replica ~$130 + Cache Basic C1 ~$55 + App Gateway ~$25 ≈ **$570** |

**LLM API cost is separate and usage-based** (the dominant variable cost). Each chat
query can trigger several model calls (router + HyDE + generate + insights). Budget
per-query token cost × expected daily volume; the semantic cache reduces repeats.
Reserved instances / savings plans cut compute ~30–60%.

---

## 6. Scaling recommendations

1. **Backend is stateless** → scale horizontally behind the LB. Sessions/denylist
   live in Redis, so any replica handles any request.
2. **Database connections:** each worker holds primary (10+20) + read-only (5+10)
   pools. With many replicas you WILL exhaust Postgres `max_connections` — put
   **PgBouncer** (transaction pooling) in front of both primary and replica.
3. **Read-only role on a replica:** point `READONLY_POSTGRES_HOST` at a read
   replica so analyst SQL never competes with writes; RLS still applies.
4. **Embeddings** are CPU-bound (now off the event loop). Under heavy `/rag/search`
   load, scale workers or extract a dedicated embedding microservice.
5. **ChromaDB** single-node is a bottleneck/SPOF at scale → migrate to a clustered
   or managed vector DB; it re-indexes from Postgres on boot so it's replaceable.
6. **Redis**: use a managed, HA instance with `maxmemory-policy allkeys-lru`.
7. **LLM concurrency/cost**: cap concurrency, keep the semantic cache warm, and
   make HyDE/insights optional under load to cut token spend.
8. **Autoscaling signal**: ALB/AppGW request count or backend CPU; keep p95 < SLO.

---

## 7. Final deployment checklist

**Secrets & config**
- [ ] `APP_ENV=production`, `APP_DEBUG=false`
- [ ] Strong, unique `SECRET_KEY`, `JWT_SECRET_KEY`, DB/Redis/Neo4j/Grafana passwords
- [ ] `LLM_API_KEY` set from secret store; old/leaked keys revoked
- [ ] `CORS_ALLOWED_ORIGINS` = exact production origin(s)
- [ ] `COOKIE_SECURE=true`, correct `COOKIE_DOMAIN`
- [ ] `PHI_ENCRYPTION_KEYS` set, stored in KMS/Key Vault, **backed up separately**
- [ ] `READONLY_POSTGRES_*` set, `REQUIRE_READONLY_ROLE=true`

**Database**
- [ ] `alembic upgrade head` applied (migrate service ran green)
- [ ] `create_readonly_role.sql` applied; startup check confirms RO writes rejected
- [ ] RLS verified (`pytest tests/integration`)
- [ ] Backups scheduled; a test restore verified (`verify_backup.sh`)

**Network / TLS**
- [ ] HTTPS only; HTTP→HTTPS redirect; HSTS present
- [ ] Datastore ports NOT internet-exposed (5432/6379/7687/8000/9090/3000)
- [ ] WAF / rate limiting at the edge (defense in depth over app rate limits)

**App / CI**
- [ ] `docker compose -f docker-compose.prod.yml config` validates
- [ ] Images built from pinned deps; `pip-audit`/`npm audit` reviewed
- [ ] `secret-scan` + unit + security + integration CI jobs green
- [ ] Frontend `/healthz` and backend `/health` return 200 behind the LB

**Observability**
- [ ] Prometheus scraping the backend; `alerts.yml` loaded; Alertmanager wired
- [ ] Grafana admin password set; dashboards load; sign-up disabled
- [ ] Log aggregation collecting structured JSON logs; PHI not logged

**DR**
- [ ] RTO/RPO documented and tested (`docs/DISASTER_RECOVERY.md`)
- [ ] Encryption keys + secrets included in the recovery runbook
