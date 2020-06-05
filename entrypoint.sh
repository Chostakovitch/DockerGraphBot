#!/bin/sh

echo export OUTPUT_PATH=${OUTPUT_PATH} >> .env

set -- 'code/dgb.py'
if [ ! -z "${CONFIG_FILE}" ]; then
  set -- "$@" "--config-file" "${CONFIG_FILE}"
fi

if [ ! -z "${OUTPUT_DIRECTORY}" ]; then
  set -- "$@" "--output-directory" "${OUTPUT_DIRECTORY}"
fi

if [ ! -z "${CERTS_DIRECTORY}" ]; then
  set -- "$@" "--certs-directory" "${CERTS_DIRECTORY}"
fi

if [ -z "${CRON_CONFIG}" ]; then
  echo "CRON_CONFIG not set, launch only once..."
  "$@"
else
  echo "Building environment variables files for cron environment..."
  echo export PATH=${PATH} >> .env
  echo export PYTHON_VERSION=${PYTHON_VERSION} >> .env
  echo "Creating crontab with ${CRON_CONFIG} specification..."
  echo "${CRON_CONFIG} . /code/.env && python $@ >/proc/1/fd/1 2>/proc/1/fd/2" >> crontab.conf
  crontab crontab.conf
  echo "Launching cron daemon..."
  cron -f -L 15
fi
