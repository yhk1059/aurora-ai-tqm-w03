# AXHub 배포용. 저장소 전체(원본 데이터 포함)를 넣고 FastAPI를 PORT로 띄운다.
FROM python:3.14-slim
WORKDIR /app
COPY w03_system/backend/requirements.txt w03_system/backend/requirements.txt
RUN pip install --no-cache-dir -r w03_system/backend/requirements.txt
COPY . .
ENV PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "uvicorn backend.api.main:app --app-dir w03_system --host 0.0.0.0 --port ${PORT}"]
