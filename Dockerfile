FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install build dependencies and Rust toolchain
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    pkg-config \
    libssl-dev \
    libffi-dev \
    git \
    && curl https://sh.rustup.rs -sSf | sh -s -- -y \
    && . "$HOME/.cargo/env"

# Add Rust/Cargo to PATH
ENV PATH="/root/.cargo/bin:${PATH}"

# Install maturin globally (required for some Rust-based Python packages)
RUN pip install --no-cache-dir maturin

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app
COPY . .

# Expose FastAPI port
EXPOSE 8000

# Launch the app
CMD ["python", "main.py"]
