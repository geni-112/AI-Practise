#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ $EUID != 0 ]]; then echo 'Run with sudo on the intended cloud host.' >&2; exit 1; fi
umask 077
install -d -m 0750 -o 1000 -g 1000 data data/uploads data/private
install -d -m 0750 -o root -g 1000 secrets
if [[ ! -e .env ]]; then cp --no-clobber .env.example .env; fi
chmod 0600 .env
secret=secrets/initial-account-password
if [[ ! -e "$secret" ]]; then
  pending=$(mktemp secrets/.initial-XXXXXXXX)
  trap 'rm -f -- "$pending"' EXIT
  openssl rand -hex 24 > "$pending"
  chown 1000:1000 "$pending"
  chmod 0400 "$pending"
  if ! ln -- "$pending" "$secret"; then test -f "$secret"; fi
fi
echo 'Configuration prepared. Complete .env and place the database CA in secrets/rds-ca.pem.'
