# KAI Deployment & Hardening Guide (V1)

Follow these steps to deploy **KAI** on your private home server.

---

## Quick Setup Guide (Under 10 Steps)

### Step 1: Install Ollama & Pull Required Models
On your host server:
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3:8b
ollama pull nomic-embed-text
```

### Step 2: Install & Connect Tailscale
Enable private Tailscale mesh networking:
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

### Step 3: Configure Environment Variables
Copy `.env.example` to `.env` and configure your credentials:
```bash
cp .env.example .env
```
Edit `.env`:
```env
KAI_OWNER_NAME=YourName
KAI_TZ=Asia/Kolkata
KAI_MODEL=qwen3:8b
OLLAMA_BASE_URL=http://host.docker.internal:11434/v1
DATABASE_URL=sqlite:////data/kai.db
NTFY_URL=https://ntfy.sh
NTFY_TOPIC=my_private_kai_topic_1234
API_TOKEN=your_secure_random_api_token
LOG_LEVEL=INFO
```

### Step 4: Clone / Copy Codebase & Create Data Directory
```bash
mkdir -p /data/kai /data/backups /data/logs
git clone <your-kai-repo> /opt/kai
cd /opt/kai
```

### Step 5: Start via Docker Compose
```bash
docker compose up -d --build
```

### Step 6: Apply Database Migrations
```bash
docker compose exec kai alembic upgrade head
```

### Step 7: Enable systemd Service (Optional Auto-start)
```bash
sudo cp kai.service /etc/systemd/system/kai.service
sudo systemctl daemon-reload
sudo systemctl enable --now kai
```

### Step 8: Verify System Health
Visit `http://<your-tailscale-ip>:8000/health` or run:
```bash
curl http://localhost:8000/health
```

### Step 9: Install PWA on Phone / Desktop
1. Open `http://<your-tailscale-ip>:8000` in Safari or Chrome on your phone over Tailscale.
2. Tap **Add to Home Screen**.
3. Open KAI from home screen, enter your `API_TOKEN` in **Settings**, and start chatting!

---

## Backup & Recovery

### Automated Nightly Backups
KAI automatically performs an online SQLite backup every night at 02:00 UTC to `/data/backups/kai_backup_YYYYMMDD_HHMMSS.db` with a strict 30-day retention policy.

### Manual Backup
```bash
docker compose exec kai python -c "from app.services.backup import perform_db_backup; perform_db_backup()"
```

### Database Restore
To list or restore backups:
```bash
docker compose exec kai python scripts/restore.py list
docker compose exec kai python scripts/restore.py restore kai_backup_YYYYMMDD_HHMMSS.db
```

---

## Logs & Audit Trail

Structured JSON logs are output to stdout and written to `/data/logs/kai.log` with automatic 10MB file rotation (keeping 5 backups).

View live logs:
```bash
docker compose logs -f kai
```
