FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libssl-dev git cmake ninja-build \
    && rm -rf /var/lib/apt/lists/*

# liboqs 0.16.0 — passt zu liboqs-python 0.16.0.1
ARG LIBOQS_VERSION=0.16.0
RUN git clone --depth 1 --branch ${LIBOQS_VERSION} \
        https://github.com/open-quantum-safe/liboqs.git /tmp/liboqs \
    && cmake -S /tmp/liboqs -B /tmp/liboqs/build -GNinja \
        -DBUILD_SHARED_LIBS=ON \
        -DCMAKE_INSTALL_PREFIX=/usr/local \
        -DOQS_USE_OPENSSL=ON \
    && cmake --build /tmp/liboqs/build \
    && cmake --install /tmp/liboqs/build \
    && rm -rf /tmp/liboqs \
    && ldconfig

ENV LD_LIBRARY_PATH=/usr/local/lib
ENV LIBOQS_INSTALL_PATH=/usr/local

WORKDIR /app
COPY pyproject.toml .
COPY src/ src/
COPY scripts/ scripts/
COPY erebos_keys/ erebos_keys/

RUN pip install --no-cache-dir -e .

ENTRYPOINT ["python", "-m", "erebos_network"]
