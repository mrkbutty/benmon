
# Example run:
#   podman run --name vdb_exporter -d --rm -p 8113 -v /proc:/proc:ro -v /results:/results:ro vdb_exporter

FROM python:3.11-slim

COPY requirements.txt .
RUN pip install psutil prometheus-client

COPY vdb_exporter.py .

ENV PYTHONUNBUFFERED=1
ENV VDB_EXPORTER_HOSTNAME=container

EXPOSE 8113/tcp
ENTRYPOINT [ "python", "./vdb_exporter.py" ]
