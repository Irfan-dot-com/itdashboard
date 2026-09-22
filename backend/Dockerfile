FROM python:3.11-slim

WORKDIR /app

# Install deps first (separate layer — only rebuilds when pyproject.toml changes)
COPY pyproject.toml .
RUN pip install --no-cache-dir -e "."

# Copy application code
COPY . .

# Make entrypoint executable
RUN chmod +x entrypoint.sh

EXPOSE 4000

ENTRYPOINT ["./entrypoint.sh"]
