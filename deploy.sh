#!/bin/zsh
set -e

cd "$(dirname "$0")"

APP_NAME="bookvocabapp"
RESOURCE_GROUP="book_vocab"
REGISTRY_NAME="bookvocab"
IMAGE_NAME="bookvocab"
IMAGE_TAG="latest"
IMAGE_REF="${REGISTRY_NAME}.azurecr.io/${IMAGE_NAME}:${IMAGE_TAG}"

echo "Building and pushing ${IMAGE_REF} to ACR..."
az acr build -r "${REGISTRY_NAME}" -t "${IMAGE_NAME}:${IMAGE_TAG}" .

echo "Updating Container App ${APP_NAME} in ${RESOURCE_GROUP}..."
az containerapp update \
  --name "${APP_NAME}" \
  --resource-group "${RESOURCE_GROUP}" \
  --image "${IMAGE_REF}"

echo "Done."
