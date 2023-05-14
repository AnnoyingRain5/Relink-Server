FROM python:3.11

WORKDIR /usr/src/

RUN git clone https://github.com/AnnoyingRain5/Relink-Server app

WORKDIR /usr/src/app

RUN pip install --no-cache-dir -r requirements.txt
RUN git submodule init; git submodule update --remote

RUN mkdir db
RUN echo "{}" > db/users.json
VOLUME ["/usr/src/app/db"]

CMD git pull; git submodule update --remote; pip install --no-cache-dir -r requirements.txt; python3 ./server.py