.PHONY: install playground run test

install:
	uv sync --link-mode=copy

playground:
	uv run --link-mode=copy adk web app --host 127.0.0.1 --port 18081 --reload_agents

run:
	uv run --link-mode=copy uvicorn app.agent_runtime_app:agent_runtime --host 127.0.0.1 --port 8080 --reload

test:
	uv run --link-mode=copy pytest
