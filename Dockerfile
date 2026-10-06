FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates && rm -rf /var/lib/apt/lists/*
# yt-dlp needs a JavaScript runtime for YouTube
COPY --from=denoland/deno:bin /deno /usr/local/bin/deno
RUN pip install --no-cache-dir -U "yt-dlp[default]" flask gunicorn
RUN useradd -m -u 1000 user
WORKDIR /app
COPY app.py .
USER user
ENV PORT=7860
EXPOSE 7860
CMD gunicorn -b 0.0.0.0:${PORT:-7860} -w 1 --threads 4 --timeout 900 app:app
