#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION_VALUE="${1:-}"

if [[ -z "${VERSION_VALUE}" ]]; then
  echo "Usage: scripts/set-version.sh <version>" >&2
  exit 2
fi

if [[ ! "${VERSION_VALUE}" =~ ^[0-9]+\.[0-9]+\.[0-9]+([-.+][0-9A-Za-z.-]+)?$ ]]; then
  echo "Invalid version: ${VERSION_VALUE}" >&2
  exit 2
fi

printf "%s\n" "${VERSION_VALUE}" > "${ROOT_DIR}/VERSION"

python_projects=(
  "apps/wotbot/pyproject.toml"
  "apps/code-executor/pyproject.toml"
)

node_projects=(
  "apps/ui"
  "apps/wot-runtime"
  "apps/virtual-servient"
)

for file in "${python_projects[@]}"; do
  perl -0pi -e 's/^version = "[^"]+"/version = "'${VERSION_VALUE}'"/m' "${ROOT_DIR}/${file}"
done

for project in "${node_projects[@]}"; do
  node -e '
const fs = require("fs");
const version = process.argv[1];
const project = process.argv[2];

function updateJson(path, updater) {
  const data = JSON.parse(fs.readFileSync(path, "utf8"));
  updater(data);
  fs.writeFileSync(path, JSON.stringify(data, null, 2) + "\n");
}

updateJson(`${project}/package.json`, (data) => {
  data.version = version;
});

const lockPath = `${project}/package-lock.json`;
if (fs.existsSync(lockPath)) {
  updateJson(lockPath, (data) => {
    data.version = version;
    if (data.packages && data.packages[""]) {
      data.packages[""].version = version;
    }
  });
}
' "${VERSION_VALUE}" "${ROOT_DIR}/${project}"
done
