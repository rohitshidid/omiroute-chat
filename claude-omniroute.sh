#!/usr/bin/env bash
#
# Launch Claude Code against the OmniRoute gateway instead of Anthropic.
#
# This is deliberately opt-in: it exports the variables for one invocation only,
# so your normal `claude` keeps using your Anthropic account. Nothing global is
# touched.
#
#   ./claude-omniroute.sh                     # interactive
#   ./claude-omniroute.sh -p "explain this"   # one-shot
#   OMNI_MODEL=oc/mimo-v2.5-free ./claude-omniroute.sh
#
set -euo pipefail

cd "$(dirname "$0")"

# Pull OMNIROUTE_* out of .env without exporting comments or blanks.
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source <(grep -E '^[A-Z_]+=' .env)
  set +a
fi

GATEWAY="${OMNIROUTE_BASE_URL:-http://localhost:20128/v1}"
ROOT="${GATEWAY%/v1}"   # Claude Code wants the bare root, with no /v1

if ! curl -sf -m 5 "$ROOT/v1/models" >/dev/null 2>&1; then
  echo "OmniRoute is not answering at $ROOT — start it with:  omniroute" >&2
  exit 1
fi

# Claude Code is entirely tool-driven, so the model has to support tool calling.
# These three were verified working; most other providers on this box are down
# or need a CLI that isn't installed. Check with:  python3 chat.py  →  /models
export ANTHROPIC_MODEL="${OMNI_MODEL:-oc/north-mini-code-free}"
export ANTHROPIC_SMALL_FAST_MODEL="${OMNI_FAST_MODEL:-oc/mimo-v2.5-free}"
export ANTHROPIC_DEFAULT_OPUS_MODEL="$ANTHROPIC_MODEL"
export ANTHROPIC_DEFAULT_SONNET_MODEL="$ANTHROPIC_MODEL"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="$ANTHROPIC_SMALL_FAST_MODEL"

export ANTHROPIC_BASE_URL="$ROOT"
# Claude Code needs a token present; the local gateway ignores its value.
export ANTHROPIC_AUTH_TOKEN="${OMNIROUTE_API_KEY:-omniroute-local}"
# Don't send telemetry//autoupdate chatter through a proxy that can't serve it.
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1

echo "→ $ANTHROPIC_MODEL via $ANTHROPIC_BASE_URL" >&2
exec claude "$@"
