#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

case "${1:-help}" in
    server)
        echo "=== Запуск API сервера (http://localhost:8000) ==="
        echo "  POST /book — бронирование билета"
        echo "  GET  /health — проверка работоспособности"
        echo ""
        uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
        ;;
    test)
        echo "=== Запуск тестового агента ==="
        uv run python agent.py
        ;;
    agent)
        echo "=== Запуск агента ==="
        uv run python agent.py -- "$@"
        ;;
    *)
        echo "Flight Booking Agent — управление"
        echo ""
        echo "Использование: ./run.sh <команда>"
        echo ""
        echo "Команды:"
        echo "  server   — запустить API сервер (port 8000)"
        echo "  test     — запустить тестовый запрос агента"
        echo "  agent    — запустить интерактивного агента"
        echo ""
        echo "Примеры:"
        echo "  ./run.sh server"
        echo "  ./run.sh test"
        echo ""
        echo "Или через uv run:"
        echo "  uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
        echo "  uv run python agent.py"
        ;;
esac
