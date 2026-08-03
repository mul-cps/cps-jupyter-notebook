#!/bin/sh
# docker/tests/run_functional_checks.sh <image-ref> <variant-name>
#
# Starts a container from <image-ref>, copies in functional_checks.sh,
# runs it for <variant-name>, always tears the container down.
set -eu
IMAGE_REF="${1:?usage: run_functional_checks.sh <image-ref> <variant-name>}"
VARIANT="${2:?usage: run_functional_checks.sh <image-ref> <variant-name>}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONTAINER_NAME="test-${VARIANT}-$$"

cleanup() {
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "Starting container from $IMAGE_REF ..."
docker run -d --name "$CONTAINER_NAME" --entrypoint sh "$IMAGE_REF" -c "sleep 600"

echo "Copying functional_checks.sh in..."
docker cp "$SCRIPT_DIR/functional_checks.sh" "$CONTAINER_NAME:/tmp/functional_checks.sh"
docker exec "$CONTAINER_NAME" chmod +x /tmp/functional_checks.sh

echo "Running checks for variant=$VARIANT ..."
docker exec "$CONTAINER_NAME" /tmp/functional_checks.sh "$VARIANT"
