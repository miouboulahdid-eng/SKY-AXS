FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash curl jq dnsutils ca-certificates whois openssl git coreutils \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY . /app
# keep container interactive for debug; actual runs call script
ENTRYPOINT ["/bin/bash"]
