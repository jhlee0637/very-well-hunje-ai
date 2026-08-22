# syntax=docker/dockerfile:1.7
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    LUNIT_GENERATION_PROMPT_PATH=/app/prompts/generation/production_tool_v8.md \
    LUNIT_RETRIEVAL_PROMPT_PATH=/app/prompts/retrieval/grounded_v1.md

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN --mount=type=secret,id=custom_ca,required=false \
    if [ -s /run/secrets/custom_ca ]; then \
        cp /run/secrets/custom_ca /usr/local/share/ca-certificates/custom-ca.crt; \
        update-ca-certificates; \
    fi && \
    pip install --no-cache-dir --disable-pip-version-check -r /app/requirements.txt

COPY app.py /app/app.py
COPY prompts/generation/production_tool_v1.md /app/prompts/generation/production_tool_v1.md
COPY prompts/generation/production_tool_v2.md /app/prompts/generation/production_tool_v2.md
COPY prompts/generation/production_tool_v3.md /app/prompts/generation/production_tool_v3.md
COPY prompts/generation/production_tool_v8.md /app/prompts/generation/production_tool_v8.md
COPY prompts/retrieval/grounded_v1.md /app/prompts/retrieval/grounded_v1.md
COPY src /app/src

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
