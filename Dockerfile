FROM python:3

LABEL maintainer="quentinduchemin@tuta.io"

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN apt-get update && \
    apt-get install -y graphviz && \
    rm -rf /var/cache/apt/archives

RUN groupadd -r graph-bot && \
    useradd -r -g graph-bot graph-bot && \
    mkdir -p /config && \
    chown -R graph-bot:graph-bot /code && \
    chmod +x /code/entrypoint.sh

COPY ./code/ /code

WORKDIR /code

USER graph-bot

ENTRYPOINT [ "/code/entrypoint.sh" ]
