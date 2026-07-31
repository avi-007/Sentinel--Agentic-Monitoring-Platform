#!/usr/bin/env bash
# Runs once on first boot (cloud-init). Installs Docker, fetches the repo,
# and starts the stack in mock mode so it comes up healthy with zero secrets.
# SSH in afterwards to edit /opt/sentinel/.env (real OPENAI/OPENROUTER key,
# Grafana password) and re-run `docker compose up -d` to pick it up.
set -euo pipefail

apt-get update -y
apt-get install -y ca-certificates curl gnupg git

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$${VERSION_CODENAME}") stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

systemctl enable --now docker
usermod -aG docker ubuntu

REPO_URL="${git_repo_url}"
if [ -n "$REPO_URL" ]; then
  git clone "$REPO_URL" /opt/sentinel
else
  mkdir -p /opt/sentinel
  echo "No git_repo_url set — upload the repo to /opt/sentinel yourself (scp/rsync), then run docker compose up -d --build there." > /opt/sentinel/README_DEPLOY.txt
fi

if [ -d /opt/sentinel ] && [ -f /opt/sentinel/.env.example ]; then
  cd /opt/sentinel
  cp .env.example .env   # LLM_PROVIDER=mock by default — no secrets needed to boot
  # Change the Grafana password before this box is reachable from the internet.
  sed -i 's/^GF_SECURITY_ADMIN_PASSWORD=.*/GF_SECURITY_ADMIN_PASSWORD=change-me/' .env
  docker compose up --build -d
fi
