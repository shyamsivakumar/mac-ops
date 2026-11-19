FROM node:22-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends git python3 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ADD snapshot.tar /app/
RUN npm install --no-audit --no-fund --ignore-scripts
RUN git init -q && git add -A && git -c user.name=snapshot -c user.email=snapshot@localhost commit -q -m snapshot
