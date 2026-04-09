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
    && conda clean --all -y && \
    conda clean --all --force-pkgs-dirs && \
    rm -rf /opt/conda/pkgs/* && \
    rm -rf /opt/conda/envs/*/lib/python*/site-packages/__pycache__

WORKDIR /app

# Copy application files
COPY speed-camera.py .
COPY camera.py .
COPY calibrate.py .
COPY requirements.txt .

# Install remaining Python dependencies via pip
RUN pip install --no-cache-dir \
    docopt \
    python-telegram-bot

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
