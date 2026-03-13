#!/bin/bash
# Start Celery worker + beat for Morning Brief
# Usage: ./scripts/start_services.sh [start|stop|status]

PROJECT_DIR="/Users/cameron/Calendar Notifier"
PYTHON="/Users/cameron/anaconda3/bin/python"
CELERY="/Users/cameron/anaconda3/bin/celery"
LOG_DIR="$PROJECT_DIR/logs"
PID_DIR="$PROJECT_DIR/pids"

mkdir -p "$LOG_DIR" "$PID_DIR"

start() {
    echo "Starting Morning Brief services..."

    # Check Redis
    if ! redis-cli ping > /dev/null 2>&1; then
        echo "ERROR: Redis is not running. Start it first: brew services start redis"
        exit 1
    fi

    # Start Celery worker
    cd "$PROJECT_DIR"
    $CELERY -A app.core.celery_app worker \
        --loglevel=info \
        --pidfile="$PID_DIR/worker.pid" \
        --logfile="$LOG_DIR/worker.log" \
        --detach \
        --concurrency=2
    echo "  Worker started (PID: $(cat "$PID_DIR/worker.pid" 2>/dev/null))"

    # Start Celery beat
    $CELERY -A app.core.celery_app beat \
        --loglevel=info \
        --pidfile="$PID_DIR/beat.pid" \
        --logfile="$LOG_DIR/beat.log" \
        --detach
    echo "  Beat started (PID: $(cat "$PID_DIR/beat.pid" 2>/dev/null))"

    echo "Services started. Logs in $LOG_DIR/"
}

stop() {
    echo "Stopping Morning Brief services..."

    if [ -f "$PID_DIR/worker.pid" ]; then
        kill $(cat "$PID_DIR/worker.pid") 2>/dev/null && echo "  Worker stopped" || echo "  Worker not running"
        rm -f "$PID_DIR/worker.pid"
    fi

    if [ -f "$PID_DIR/beat.pid" ]; then
        kill $(cat "$PID_DIR/beat.pid") 2>/dev/null && echo "  Beat stopped" || echo "  Beat not running"
        rm -f "$PID_DIR/beat.pid"
    fi
}

status() {
    echo "Morning Brief service status:"

    # Redis
    if redis-cli ping > /dev/null 2>&1; then
        echo "  Redis:  ✅ running"
    else
        echo "  Redis:  ❌ not running"
    fi

    # Worker
    if [ -f "$PID_DIR/worker.pid" ] && kill -0 $(cat "$PID_DIR/worker.pid") 2>/dev/null; then
        echo "  Worker: ✅ running (PID $(cat "$PID_DIR/worker.pid"))"
    else
        echo "  Worker: ❌ not running"
    fi

    # Beat
    if [ -f "$PID_DIR/beat.pid" ] && kill -0 $(cat "$PID_DIR/beat.pid") 2>/dev/null; then
        echo "  Beat:   ✅ running (PID $(cat "$PID_DIR/beat.pid"))"
    else
        echo "  Beat:   ❌ not running"
    fi
}

case "${1:-start}" in
    start)  start ;;
    stop)   stop ;;
    restart) stop; sleep 2; start ;;
    status) status ;;
    *)      echo "Usage: $0 {start|stop|restart|status}" ;;
esac
