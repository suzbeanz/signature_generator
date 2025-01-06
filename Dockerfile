FROM python:3.10-slim-buster

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Copy the credentials file
COPY credentials/credentials.json /app/credentials/credentials.json

# Set environment variables
# ENV GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/credentials.json

# Expose the port the app runs on
EXPOSE 8080

# Run the application
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]
