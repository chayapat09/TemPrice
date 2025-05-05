# Dockerfile

# 1. Use an official Python runtime as a parent image
# Using slim version for smaller size
FROM python:3.11-slim

# 2. Set environment variables
# Prevents Python from writing pyc files to disc
ENV PYTHONDONTWRITEBYTECODE 1
# Prevents Python from buffering stdout/stderr
ENV PYTHONUNBUFFERED 1
# Set the Flask environment to production (can be overridden by compose)
ENV FLASK_ENV production
# Set the working directory in the container
WORKDIR /app

# 3. Install system dependencies if needed
# Example: If pandas/numpy need build tools (uncomment if build fails)
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     build-essential \
#     && rm -rf /var/lib/apt/lists/*

# 4. Install Python dependencies
# Copy only the requirements file first to leverage Docker cache
COPY requirements.txt .
# Use --no-cache-dir to reduce image size and upgrade pip
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 5. Copy the application code into the container
# Copy everything from the current directory (.) into the container's WORKDIR (/app)
# .dockerignore will prevent copying excluded files/folders
COPY . .

# 6. (Optional but Recommended) Create a non-root user to run the application
# RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser
# RUN chown -R appuser:appuser /app # Ensure ownership
# USER appuser
# Note: If using a non-root user, ensure file permissions allow writing to /app/instance
# If you mount instance from host, host permissions matter more.

# 7. Expose the port the app runs on (defined in config.py as 8082)
EXPOSE 8082

# 8. Define the command to run the application using waitress (Production WSGI Server)
# waitress-serve --host=0.0.0.0 binds to all interfaces inside the container
# --port=8082 matches the exposed port and config.py
# app:app tells waitress to look for the 'app' object in the 'app.py' file
CMD ["waitress-serve", "--host=0.0.0.0", "--port=8082", "app:app"]