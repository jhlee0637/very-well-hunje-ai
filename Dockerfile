FROM python:3.13-slim

WORKDIR /app
COPY app.py /app/app.py
COPY prompting.py /app/prompting.py
COPY tests/fixtures/retrieval /app/tests/fixtures/retrieval

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["python", "app.py"]
