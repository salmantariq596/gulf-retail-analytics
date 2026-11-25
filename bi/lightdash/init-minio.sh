#!/bin/sh
# From github.com/lightdash/lightdash/blob/main/docker/init-minio.sh (trimmed):
# start MinIO, create the results bucket, expire query results after N days.
set -e

minio server /data --console-address ":9001" &

until mc alias set local http://localhost:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" 2>/dev/null; do
  sleep 1
done

IFS=','
for bucket in $MINIO_DEFAULT_BUCKETS; do
  if [ -n "$bucket" ]; then
    mc mb -p local/"$bucket" 2>/dev/null || echo "Bucket '$bucket' already exists"
    mc ilm rule rm --all --force local/"$bucket" 2>/dev/null || true
    mc ilm rule add --expire-days "${MINIO_EXPIRATION_DAYS:-1}" local/"$bucket" 2>/dev/null || true
  fi
done

wait
