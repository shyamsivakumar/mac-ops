#!/usr/bin/env bash
set -eu

# shellcheck source=/dev/null
. "$(dirname -- "$0")/common.sh"

"$COLIMA" status woodpecker >/dev/null
compose config --quiet
[ "$(stat -f '%Lp' "$ROOT/.env")" = "600" ] || {
  echo ".env must have mode 600." >&2
  exit 1
}

deadline=$((SECONDS + 120))
until curl -fsS http://127.0.0.1:8000/healthz >/dev/null 2>&1; do
  if [ "$SECONDS" -ge "$deadline" ]; then
    compose ps
    compose logs --tail=80 server agent-linux agent-deploy >&2
    echo "Woodpecker server did not become healthy." >&2
    exit 1
  fi
  sleep 2
done

deadline=$((SECONDS + 30))
until {
  all_running=true
  for service in server agent-linux agent-deploy webhook-proxy; do
    if [ -z "$(compose ps --status running -q "$service")" ]; then
      all_running=false
    fi
  done
  "$all_running"
}; do
  if [ "$SECONDS" -ge "$deadline" ]; then
    compose ps >&2
    compose logs --tail=80 server agent-linux agent-deploy >&2
    echo "Woodpecker services did not remain running." >&2
    exit 1
  fi
  sleep 2
done

deadline=$((SECONDS + 120))
until compose logs --tail=100 agent-linux 2>&1 | grep -q '"parallel workflows":3'; do
  if [ "$SECONDS" -ge "$deadline" ]; then
    echo "ci-linux agent did not report parallel workflows:3." >&2
    compose logs --tail=100 agent-linux >&2
    exit 1
  fi
  sleep 2
done

deadline=$((SECONDS + 120))
until compose logs --tail=100 agent-deploy 2>&1 | grep -q '"parallel workflows":1'; do
  if [ "$SECONDS" -ge "$deadline" ]; then
    echo "ci-deploy agent did not report parallel workflows:1." >&2
    compose logs --tail=100 agent-deploy >&2
    exit 1
  fi
  sleep 2
done

if ! docker run --rm -v woodpecker-ci-agent-linux-config:/config alpine:3.22 \
  test -s /config/agent.conf; then
  echo "ci-linux agent identity was not persisted." >&2
  exit 1
fi

if ! docker run --rm -v woodpecker-ci-agent-deploy-config:/config alpine:3.22 \
  test -s /config/agent.conf; then
  echo "ci-deploy agent identity was not persisted." >&2
  exit 1
fi

public_host=$(sed -n 's/^WOODPECKER_WEBHOOK_HOST=//p' "$ROOT/.env")
private_host=$(sed -n 's/^WOODPECKER_HOST=//p' "$ROOT/.env")
public_code=$(curl -ksS -o /dev/null -w '%{http_code}' "$public_host/")
if [ "$public_code" != "404" ]; then
  printf 'Public ingress must return 404 outside the webhook path; got %s.\n' "$public_code" >&2
  exit 1
fi

for public_probe in authorize api/user; do
  public_probe_code=$(curl -ksS -X POST -o /dev/null -w '%{http_code}' \
    "$public_host/$public_probe")
  if [ "$public_probe_code" != "404" ]; then
    printf 'Public ingress exposed /%s with status %s.\n' "$public_probe" "$public_probe_code" >&2
    exit 1
  fi
done

public_hook_get_code=$(curl -ksS -o /dev/null -w '%{http_code}' \
  "$public_host/api/hook")
if [ "$public_hook_get_code" != "404" ]; then
  printf 'Public webhook path accepted GET with status %s.\n' "$public_hook_get_code" >&2
  exit 1
fi

private_code=$(curl -ksS -o /dev/null -w '%{http_code}' "$private_host/healthz")
case "$private_code" in
  2??) ;;
  *)
    printf 'Private Tailscale health endpoint returned %s.\n' "$private_code" >&2
    exit 1
    ;;
esac

server_ports=$(docker inspect --format '{{json .HostConfig.PortBindings}}' "$(compose ps -q server)")
case "$server_ports" in
  *'"HostIp":"127.0.0.1"'*) ;;
  *)
    printf 'Server is not bound only to localhost: %s\n' "$server_ports" >&2
    exit 1
    ;;
esac

for agent_svc in agent-linux agent-deploy; do
  agent_mounts=$(docker inspect --format '{{range .Mounts}}{{println .Source "->" .Destination}}{{end}}' "$(compose ps -q "$agent_svc")")
  case "$agent_mounts" in
    *'/var/run/docker.sock -> /var/run/docker.sock'*) ;;
    *)
      printf '%s Docker socket mount is missing:\n%s\n' "$agent_svc" "$agent_mounts" >&2
      exit 1
      ;;
  esac
  case "$agent_mounts" in
    *'woodpecker-ci-agent-secret-data'*'-> /run/secrets'*) ;;
    *)
      printf '%s secret mount is missing:\n%s\n' "$agent_svc" "$agent_mounts" >&2
      exit 1
      ;;
  esac
  case "$agent_mounts" in
    *'-> /etc/woodpecker'*) ;;
    *)
      printf '%s identity mount is missing:\n%s\n' "$agent_svc" "$agent_mounts" >&2
      exit 1
      ;;
  esac
  case "$agent_mounts" in
    *'woodpecker-ci-server-secret-data'*)
      printf '%s must not mount GitHub OAuth secrets.\n' "$agent_svc" >&2
      exit 1
      ;;
  esac
done

printf 'Local health: OK\n'
printf 'Containers: server, ci-linux (cap 3), ci-deploy (cap 1, role=deploy), webhook filter\n'
printf 'Private host: %s\n' "$(sed -n 's/^WOODPECKER_HOST=//p' "$ROOT/.env")"
printf 'Public ingress: POST /api/hook only\n'
printf 'OAuth callback: %s/authorize\n' "$(sed -n 's/^WOODPECKER_HOST=//p' "$ROOT/.env")"
