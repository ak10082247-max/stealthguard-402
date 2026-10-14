FROM python:3.11-slim

WORKDIR /usr/src/app

# Install Python packages
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

ENV PYTHONUNBUFFERED=1
ENV PORT=8000

EXPOSE 8000

# Default entrypoint smart-routes between Apify Cloud Actor run and Render/Railway Web Service
CMD ["sh", "-c", "if [ \"$APIFY_IS_AT_HOME\" = \"1\" ] || [ \"$APIFY_IS_AT_HOME\" = \"true\" ]; then python apify_main.py; else uvicorn src.api:app --host 0.0.0.0 --port ${PORT:-8000}; fi"]
