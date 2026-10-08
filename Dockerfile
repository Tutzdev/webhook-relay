FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
RUN useradd --create-home relay

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN DJANGO_SECRET_KEY=collectstatic-only python manage.py collectstatic --noinput

USER relay
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
