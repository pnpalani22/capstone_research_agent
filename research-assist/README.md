# Research Assist Spring Boot Proxy

This project wraps the existing LangGraph Python backend with a Spring Boot proxy layer. It preserves the current API contract while keeping the original Python backend files untouched.

## Overview

- The Python backend remains in the parent repository root.
- `research-assist` provides a Spring Boot application that forwards API requests to the Python FastAPI service.
- The Spring Boot proxy uses the same endpoint patterns as the original `api.py` service.

## Requirements

- Java 17+
- Maven wrapper is included, so `./mvnw` can be used without a separate Maven install.
- Python backend should be running at `http://localhost:8000`.

## Run

From `research-assist`:

```powershell
./mvnw spring-boot:run
```

## API

- `GET /api/health`
- `POST /api/sessions`
- `POST /api/runs/start`
- `GET /api/runs/{threadId}`
- `POST /api/runs/resume`
- `POST /api/translate`

## Notes

- The Python backend still handles LangGraph state, prompts, tools, and model calls.
- `spring.jackson.property-naming-strategy=SNAKE_CASE` is configured for API compatibility.
