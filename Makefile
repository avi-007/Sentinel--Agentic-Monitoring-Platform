.PHONY: up down build logs ps psql grafana restart-agent clean

up:
	docker compose up --build -d

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f generator detector agent

ps:
	docker compose ps

psql:
	docker compose exec postgres psql -U sentinel -d sentinel

grafana:
	open http://localhost:3000

restart-agent:
	docker compose up -d --build agent

clean:
	docker compose down -v
