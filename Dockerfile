FROM python:3.12-slim
WORKDIR /app
COPY server/requirements.txt /app/server/requirements.txt
RUN pip install --no-cache-dir -r /app/server/requirements.txt
COPY server /app/server
COPY web /app/web
ENV PYTHONPATH=/app/server
ENV PORT=10000
EXPOSE 10000
CMD ["sh", "-c", "uvicorn app.main:app --app-dir /app/server --host 0.0.0.0 --port ${PORT:-10000} --proxy-headers"]
