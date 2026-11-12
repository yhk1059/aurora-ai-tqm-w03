# AXHub 배포용. 1단계에서 화면을 빌드하고, 2단계에서 저장소 전체(원본 데이터 포함)와 빌드 결과를 넣어
# FastAPI가 화면과 API를 함께 PORT로 내보낸다.
FROM node:22-slim AS frontend
WORKDIR /app/w03_system/frontend
COPY w03_system/frontend/package.json w03_system/frontend/package-lock.json ./
RUN npm ci
COPY w03_system/frontend/ ./
RUN npm run build

FROM python:3.14-slim
WORKDIR /app
COPY w03_system/backend/requirements.txt w03_system/backend/requirements.txt
RUN pip install --no-cache-dir -r w03_system/backend/requirements.txt
COPY . .
COPY --from=frontend /app/w03_system/frontend/dist w03_system/frontend/dist
ENV PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "uvicorn backend.api.main:app --app-dir w03_system --host 0.0.0.0 --port ${PORT}"]
