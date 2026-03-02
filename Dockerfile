# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies required for some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    locales \
    && rm -rf /var/lib/apt/lists/*

# Set locale for Russian language support
RUN sed -i 's/# ru_RU.UTF-8 UTF-8/ru_RU.UTF-8 UTF-8/' /etc/locale.gen && \
    locale-gen

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY *.py ./

# Create necessary directories
RUN mkdir -p Logs

# Create empty users.json file
RUN echo "{}" > users.json

# Expose port (not used for polling bot but good practice)
EXPOSE 8080

# Run the bot - API key must be provided via TELEGRAM_API_KEY environment variable
CMD ["sh", "-c", "echo $TELEGRAM_API_KEY > api_key_journal_unitech.txt && python rasp_unitech.py"]
