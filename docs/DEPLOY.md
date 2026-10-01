# Deploying Trivia Master

Backend on an AWS EC2 server (Docker Compose, Caddy for HTTPS). Frontend on AWS Amplify as static files.

```
Browser ──> Amplify (static frontend)
   └──────> https://<name>.duckdns.org ──> Caddy ──> FastAPI + ChromaDB   (EC2, Docker)
```

## 0. Before you start

- Push the repo to GitHub. Never commit `backend/.env`.
- **Cap the LLM bill.** DeepSeek is prepaid, so only top up a small amount (for example $5). The backend also has demo limits (see `backend/.env.example`).
- **AWS budget alert:** Billing console, Budgets, create a monthly cost budget (for example $10) with an email alert.
- AWS free plan accounts close after 6 months or when the credits run out. Upgrade to a paid plan before then if the demo should stay online.

## 1. Get a free domain (DuckDNS)

Sign in at https://www.duckdns.org and create a subdomain, for example `trivia-master`. Leave the IP for now.

## 2. Launch the server (EC2)

In the EC2 console, **Launch instance**:

| Setting | Value |
|---|---|
| Image | Ubuntu Server 24.04 LTS |
| Instance type | `t3.small` (2 GB memory; free plan eligible) |
| Key pair | create one and keep the `.pem` file safe |
| Storage | 20 GB gp3 |
| Security group | SSH (22) from **My IP** only; HTTP (80) and HTTPS (443) from anywhere |

Then **Elastic IPs**, allocate one and associate it with the instance, so the address never changes. Put that IP into your DuckDNS subdomain.

## 3. Set up the server

Connect (from the folder with the `.pem` file):

On Windows, SSH refuses a key file other users can read. Fix it once in cmd:

```
icacls trivia-key.pem /inheritance:r
icacls trivia-key.pem /grant:r "%USERNAME%":R
icacls trivia-key.pem /remove "NT AUTHORITY\Authenticated Users" "BUILTIN\Users" "Everyone"
```

If SSH later times out, your home IP probably changed: set the SSH rule's source to **My IP** again.

```bash
ssh -i trivia-key.pem ubuntu@<elastic-ip>
```

Install Docker and add 2 GB of swap as a safety margin:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
exit    # log out and back in so the docker group applies
```

Get the code and create the two settings files:

```bash
git clone https://github.com/<you>/trivia-master.git
cd trivia-master
cp backend/.env.example backend/.env
nano backend/.env      # set LLM_PROVIDER, the API key, and the demo limits
echo "DOMAIN=trivia-master.duckdns.org" > .env
```

Start it:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

The first build takes a few minutes. Check https://trivia-master.duckdns.org/health in a browser. It should return `"status": "ok"`. Caddy gets the HTTPS certificate on its own; if it fails, check that DuckDNS points to the Elastic IP and ports 80 and 443 are open.

## 4. Deploy the frontend (Amplify)

In the Amplify console: **Create new app**, GitHub, pick the repo and branch. Amplify reads `amplify.yml` from the repo.

- Tick **My app is a monorepo** and set the root to `frontend`.
- Environment variables:
  - `NEXT_PUBLIC_API_URL` = `https://trivia-master.duckdns.org`
  - `AMPLIFY_MONOREPO_APP_ROOT` = `frontend`

Deploy. You get an address like `https://main.d1234abcd.amplifyapp.com`.

**If the deploy fails with `Can't find required-server-files.json`:** Amplify set the app up as a server-rendered Next.js app. Switch it to static hosting in CloudShell (the `>_` icon in the AWS console), using your app ID (the `d...` part of the address) and branch name, then redeploy:

```bash
aws amplify update-app --app-id <app-id> --platform WEB
aws amplify update-branch --app-id <app-id> --branch-name main --framework "Web"
```

## 5. Connect the two

The backend only accepts requests from the frontend's address. On the server:

```bash
nano backend/.env      # FRONTEND_ORIGINS=https://main.d1234abcd.amplifyapp.com
docker compose -f docker-compose.prod.yml up -d --force-recreate backend
```

Open the Amplify address and play a game. A CORS error in the browser console means `FRONTEND_ORIGINS` doesn't exactly match the Amplify address (check `https://` and no trailing slash).

## Everyday commands (on the server)

```bash
docker compose -f docker-compose.prod.yml logs -f backend     # watch the game log
docker compose -f docker-compose.prod.yml ps                  # status
git pull && docker compose -f docker-compose.prod.yml up -d --build   # deploy a new version
```

Pushing to GitHub redeploys the frontend on Amplify automatically.
