#!/usr/bin/env bash
ROOT="$HOME/Desktop/360_image_processing/DigitalTwin"
case "$1" in
  start)
    pg_ctl -D "$ROOT/.localdb/pg" -o "-p 5432 -k /tmp" -l "$ROOT/.localdb/pg/server.log" start
    redis-server --port 6379 --dir "$ROOT/.localdb/redis" --daemonize yes
    echo "Postgres + Redis started." ;;
  stop)
    pg_ctl -D "$ROOT/.localdb/pg" stop
    redis-cli -p 6379 shutdown nosave 2>/dev/null
    echo "Stopped." ;;
  status)
    pg_ctl -D "$ROOT/.localdb/pg" status
    redis-cli -p 6379 ping ;;
  *) echo "usage: bash services.sh {start|stop|status}" ;;
esac