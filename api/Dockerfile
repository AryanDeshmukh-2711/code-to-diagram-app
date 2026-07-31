# Build context is the REPO ROOT, not api/ — the image needs shared/ so that the
# CPM has exactly one definition across api and worker.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

# Editable installs so the bind mounts in docker-compose stay live under --reload.
COPY shared/ /srv/shared/
RUN pip install --no-cache-dir -e "/srv/shared[dev]"

COPY api/ /srv/api/
RUN pip install --no-cache-dir -e "/srv/api[dev]"

WORKDIR /srv/api
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
