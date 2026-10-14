FROM python:3.11-slim

WORKDIR /usr/src/app

# Install Python packages
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

ENV PYTHONUNBUFFERED=1
ENV PORT=10000

EXPOSE 10000

CMD ["sh", "-c", "if [ \"$APIFY_IS_AT_HOME\" = \"1\" ] || [ -n \"$APIFY_ACT_ID\" ]; then python apify_main.py; else uvicorn src.api:app --host 0.0.0.0 --port ${PORT:-10000}; fi"]

