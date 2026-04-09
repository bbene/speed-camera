FROM continuumio/miniconda3:latest

# Install Python packages via conda (includes OpenCV with all dependencies)
# Aggressive cleanup to minimize image size
RUN conda install -y -c conda-forge \
    python=3.11 \
    opencv \
    numpy \
    scipy \
    pyyaml \
    pillow \
    imagemagick \
    psycopg2 \
    && conda clean --all -y && \
    conda clean --all --force-pkgs-dirs && \
    rm -rf /opt/conda/pkgs/* && \
    rm -rf /opt/conda/envs/*/lib/python*/site-packages/__pycache__

# Install build dependencies for psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy application files
COPY speed-camera.py .
COPY camera.py .
COPY calibrate.py .
COPY models.py .
COPY database.py .
COPY requirements.txt .

# Copy web interface files
COPY templates/ templates/
COPY static/ static/

# Install only the new packages via pip (Flask, SQLAlchemy, python-dotenv, docopt)
# psycopg2 is installed via conda for better compatibility
RUN pip install --no-cache-dir \
    Flask==3.0.0 \
    SQLAlchemy==2.0.0 \
    python-dotenv==1.0.0 \
    docopt==0.6.2

# Create directories for logs and data
RUN mkdir -p logs data

# Create non-root user for security
RUN useradd -m -u 1000 speedcamera && \
    chown -R speedcamera:speedcamera /app

USER speedcamera

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Default config file location
ENV CONFIG_FILE=/app/config.yaml

# Run the speed camera application
CMD ["python", "speed-camera.py", "--config", "/app/config.yaml"]
