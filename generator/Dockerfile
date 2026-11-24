FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir "fastapi>=0.116" "uvicorn[standard]>=0.30"

COPY mock_api/ ./mock_api/

EXPOSE 8000
CMD ["uvicorn", "mock_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
