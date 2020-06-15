FROM python:3

ENV SUPERCRONIC_URL=https://github.com/aptible/supercronic/releases/download/v0.1.9/supercronic-linux-amd64 \
    SUPERCRONIC=supercronic-linux-amd64 \
    SUPERCRONIC_SHA1SUM=5ddf8ea26b56d4a7ff6faecdd8966610d5cb9d85

LABEL maintainer="quentinduchemin@tuta.io"

RUN apt-get update \
    && apt-get install -y graphviz curl \
    && rm -rf /var/cache/apt/archives

RUN curl -fsSLO "$SUPERCRONIC_URL" \
    && echo "${SUPERCRONIC_SHA1SUM}  ${SUPERCRONIC}" | sha1sum -c - \
    && chmod +x "$SUPERCRONIC" \
    && mv "$SUPERCRONIC" "/usr/local/bin/${SUPERCRONIC}" \
    && ln -s "/usr/local/bin/${SUPERCRONIC}" /usr/local/bin/supercronic

COPY entrypoint.sh requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

COPY ./code/ /code
RUN chmod +x /entrypoint.sh
WORKDIR /code

CMD [ "/entrypoint.sh" ]
