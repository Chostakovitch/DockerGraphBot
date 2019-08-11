FROM python:3

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN apt-get update && \
    apt-get install -y graphviz && \
    rm -rf /var/cache/apt/archives

COPY main.py ./

RUN groupadd -r graph-bot && \
    useradd -r -g graph-bot graph-bot
USER graph-bot

CMD [ "python", "./main.py" ]
