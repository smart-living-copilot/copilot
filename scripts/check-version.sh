#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION_VALUE="$(tr -d '[:space:]' < "${ROOT_DIR}/VERSION")"

if [[ -z "${VERSION_VALUE}" ]]; then
  echo "VERSION is empty" >&2
  exit 1
fi

if [[ ! "${VERSION_VALUE}" =~ ^[0-9]+\.[0-9]+\.[0-9]+([-.+][0-9A-Za-z.-]+)?$ ]]; then
  echo "VERSION is invalid: ${VERSION_VALUE}" >&2
  exit 1
fi

status=0

check_equal() {
  local path="$1"
  local actual="$2"
  if [[ "${actual}" != "${VERSION_VALUE}" ]]; then
    echo "${path}: expected ${VERSION_VALUE}, got ${actual}" >&2
    status=1
  fi
}

read_pyproject_version() {
  sed -n 's/^version = "\([^"]*\)"/\1/p' "$1" | head -n 1
}

read_package_version() {
  node -e 'const fs=require("fs"); const data=JSON.parse(fs.readFileSync(process.argv[1],"utf8")); process.stdout.write(data.version || "");' "$1"
}

check_equal "apps/copilot/pyproject.toml" \
  "$(read_pyproject_version "${ROOT_DIR}/apps/copilot/pyproject.toml")"
check_equal "apps/code-executor/pyproject.toml" \
  "$(read_pyproject_version "${ROOT_DIR}/apps/code-executor/pyproject.toml")"

for project in apps/ui apps/wot-runtime apps/virtual-servient; do
  check_equal "${project}/package.json" \
    "$(read_package_version "${ROOT_DIR}/${project}/package.json")"
  check_equal "${project}/package-lock.json" \
    "$(read_package_version "${ROOT_DIR}/${project}/package-lock.json")"
done

if [[ "${GITHUB_REF_TYPE:-}" == "tag" ]]; then
  expected_tag="v${VERSION_VALUE}"
  if [[ "${GITHUB_REF_NAME:-}" != "${expected_tag}" ]]; then
    echo "Git tag mismatch: expected ${expected_tag}, got ${GITHUB_REF_NAME:-<unset>}" >&2
    status=1
  fi
fi

exit "${status}"
