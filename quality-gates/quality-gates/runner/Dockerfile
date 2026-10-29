FROM python:3.12-slim
# trust an optional corporate TLS-inspection root CA (e.g. Netskope) for pip installs behind MITM proxies
COPY corporate-ca.pem /usr/local/share/ca-certificates/corporate-ca.crt
RUN update-ca-certificates
ENV PIP_CERT=/etc/ssl/certs/ca-certificates.crt
RUN pip install --no-cache-dir pyyaml==6.0.2
WORKDIR /work
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
