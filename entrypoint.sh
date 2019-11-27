#!/bin/sh

echo "Building environment variables files for cron environment..."
echo export CONFIG_PATH=${CONFIG_PATH} >> .env
echo export OUTPUT_PATH=${OUTPUT_PATH} >> .env
echo export PATH=${PATH} >> .env
echo export PYTHON_VERSION=${PYTHON_VERSION} >> .env
echo "Creating crontab..."
echo "${CRON_CONFIG} . /code/.env && python /code/main.py >/proc/1/fd/1 2>/proc/1/fd/2" >> crontab.conf
crontab crontab.conf
echo "Launching cron daemon..."
cron -f -L 15
