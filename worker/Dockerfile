# Build context is the REPO ROOT — the worker needs the same shared/ CPM
# package the api uses. One definition, two images.
FROM python:3.12-slim 

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

COPY shared/ /srv/shared/
RUN pip install --no-cache-dir -e /srv/shared

COPY worker/ /srv/worker/
RUN pip install --no-cache-dir -e "/srv/worker[dev]"

WORKDIR /srv/worker

CMD ["arq", "worker.main.WorkerSettings"]
