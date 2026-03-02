# Use Python Alpine image for a lightweight container
FROM python:3.11-alpine

# Set working directory
WORKDIR /app

# Install system dependencies required for some Python packages
RUN apk add --no-cache gcc musl-dev libffi-dev openssl-dev

# Copy requirements file first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p Logs

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Expose port (if needed for future HTTP server features)
EXPOSE 8080

# Run the bot
CMD ["python", "rasp_unitech.py"]
