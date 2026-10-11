FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-eng libpq-dev gcc curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create the non-root user, fix Windows line endings in the entrypoint
RUN useradd -m -u 10001 appuser \
    && mkdir -p uploads \
    && sed -i 's/\r$//' docker-entrypoint.sh \
    && chmod +x docker-entrypoint.sh

# Generate the Prisma client as root (it must write into site-packages),
# but keep its cache in appuser's home so appuser can use it at runtime.
RUN HOME=/home/appuser prisma generate \
    && chown -R appuser:appuser /home/appuser /app

USER appuser

EXPOSE 8000

CMD ["./docker-entrypoint.sh"]