FROM python:3

LABEL maintainer="quentinduchemin@tuta.io"

COPY requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt
RUN apt-get update && \
    apt-get install -y graphviz && \
    rm -rf /var/cache/apt/archives

COPY ./code/ /code

RUN chmod +x /code/entrypoint.sh
WORKDIR /code

ENTRYPOINT [ "/code/entrypoint.sh" ]
