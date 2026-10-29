FROM python:3.12-slim
# trust an optional corporate TLS-inspection root CA (e.g. Netskope) for pip installs behind MITM proxies
COPY corporate-ca.pem /usr/local/share/ca-certificates/corporate-ca.crt
RUN update-ca-certificates
ENV PIP_CERT=/etc/ssl/certs/ca-certificates.crt
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd -m app
COPY app.py .
USER app
CMD ["gunicorn", "-b", "0.0.0.0:8080", "app:app"]
