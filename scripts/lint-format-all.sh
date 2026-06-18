#!/usr/bin/env bash
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PYTHON_PROJECTS=(
  "apps/copilot"
  "apps/code-executor"
)

NPM_PROJECTS=(
  "apps/ui"
  "apps/wot-runtime"
  "apps/virtual-servient"
)

if [[ -n "${RUFF:-}" ]]; then
  RUFF_BIN="${RUFF}"
elif [[ -x "${ROOT_DIR}/.venv/bin/ruff" ]]; then
  RUFF_BIN="${ROOT_DIR}/.venv/bin/ruff"
else
  RUFF_BIN="ruff"
fi

status=0

run() {
  echo "+ $*"
  "$@"
  local code=$?
  if [[ ${code} -ne 0 ]]; then
    status=1
    echo "Command failed (${code}): $*" >&2
  fi
}

for project in "${PYTHON_PROJECTS[@]}"; do
  run "${RUFF_BIN}" check "${ROOT_DIR}/${project}"
  run "${RUFF_BIN}" format "${ROOT_DIR}/${project}"
done

for project in "${NPM_PROJECTS[@]}"; do
  pushd "${ROOT_DIR}/${project}" >/dev/null || {
    status=1
    echo "Failed to enter ${project}" >&2
    continue
  }
  run npm run lint
  run npm run format
  popd >/dev/null || exit 1
done

exit "${status}"
