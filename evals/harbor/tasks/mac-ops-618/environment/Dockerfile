FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates gh python3 python3-pip python3-pytest && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ADD snapshot.tar /app/
RUN git init -q && git add -A && git -c user.name=snapshot -c user.email=snapshot@localhost commit -q -m snapshot
