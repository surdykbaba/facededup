#!/bin/bash
set -e

echo "================================================"
echo "  FaceDedup API - Production Deployment"
echo "================================================"
echo ""

COMPOSE_FILE="docker-compose.prod.yaml"

# Check .env exists
if [ ! -f .env ]; then
    echo "ERROR: .env file not found. Copy .env.example and configure it."
    exit 1
fi

echo "[1/6] Pulling latest code..."
git pull origin main 2>/dev/null || echo "  Skipped pull (first deploy or no remote)."

echo "[2/6] Building Docker images..."
docker compose -f "$COMPOSE_FILE" build

echo "[3/6] Stopping existing services..."
docker compose -f "$COMPOSE_FILE" down

echo "[4/6] Starting services..."
docker compose -f "$COMPOSE_FILE" up -d --remove-orphans

echo "[5/6] Waiting for database to be ready..."
for i in $(seq 1 30); do
    if docker compose -f "$COMPOSE_FILE" exec postgres pg_isready -U "${DB_USER:-facededup}" > /dev/null 2>&1; then
        echo "  Database is ready."
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "ERROR: Database failed to start within 30 seconds."
        docker compose -f "$COMPOSE_FILE" logs postgres
        exit 1
    fi
    sleep 1
done

echo "[6/6] Running database migrations..."
docker compose -f "$COMPOSE_FILE" exec api alembic upgrade head

echo ""
echo "================================================"
echo "  Deployment complete!"
echo "================================================"
echo ""
echo "  Health: curl -s https://yourdomain.com/api/v1/health | python3 -m json.tool"
echo "  Logs:   docker compose -f $COMPOSE_FILE logs -f api"
echo "  Status: docker compose -f $COMPOSE_FILE ps"
echo ""
