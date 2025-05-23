# Use an official Python runtime
FROM python:slim

# Set environment vars
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN mkdir -p /data

# Create working directory
WORKDIR /app

# Copy files
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY rapla2ics.py .

# Expose port
EXPOSE 8080

# Run the server
CMD ["python", "rapla2ics.py"]