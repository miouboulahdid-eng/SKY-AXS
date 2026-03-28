set -e
cp docker-compose.yml docker-compose.backup.yml

cat > api_fixed.yml <<'EOC'
  image: sky_axs_final:latest
  container_name: sky_axs_initial-api
  environment:
    - REDIS_HOST=redis
    - REDIS_PORT=6379
    - RQ_QUEUE=default
    - PORT=8081
  depends_on:
    - redis
    - worker
  ports:
    - "8081:8081"
  restart: unless-stopped
EOC
awk '
/^api:/ {print; system("cat api_fixed.yml"); skip=1; next}
skip && /^[^[:space:]]/ {skip=0}
!skip {print}
' docker-compose.yml > docker-compose.fixed.yml

mv docker-compose.fixed.yml docker-compose.yml
rm -f api_fixed.yml
echo "✅ تم إصلاح قسم API بنجاح!"
