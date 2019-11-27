FROM python:3

LABEL maintainer="quentinduchemin@tuta.io"

RUN apt-get update && \
    apt-get install -y graphviz cron && \
    rm -rf /var/cache/apt/archives

COPY entrypoint.sh requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

COPY ./code/ /code
RUN chmod +x /entrypoint.sh
WORKDIR /code

CMD [ "/entrypoint.sh" ]
