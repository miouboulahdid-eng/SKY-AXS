#!/bin/sh
CURL_OPTS_DEFAULT="-sS -L --max-time 10 -A 'AXS-Sandbox/1.0'"
poc_result(){ echo "Result: $1"; printf "Confidence: %.2f\n" "$2"; [ -n "${3:-}" ] && echo "Note: $3"; }
require_confirmation(){ if [ "${AXS_DRY_RUN:-0}" = "1" ] || [ "${AXS_CONFIRM:-0}" != "1" ]; then echo "DRY-RUN or NO CONFIRM: Set AXS_CONFIRM=1 to allow live checks." >&2; return 1; fi; return 0; }
detect_sql_error(){ echo "$1" | grep -iE "syntax error|sql syntax|mysql|sqlite|psql|odbc|error in your sql|unterminated string" >/dev/null 2>&1; return $?; }
curl_get(){ local url="$1"; local opts="${CURL_OPTS:-$CURL_OPTS_DEFAULT}"; curl $opts "$url" || echo ""; }
poc_sleep(){ sleep 0.5; }
