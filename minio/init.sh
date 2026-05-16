set -e

echo ">>> Инициализация MinIO..."

# Ждём доступности
until mc alias set myminio http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" 2>/dev/null; do
  echo "Waiting for MinIO..."
  sleep 2
done

echo ">>> Создаём бакет..."
mc mb -p myminio/images

echo ">>> Создаём политику для основного сервиса..."
mc admin policy create myminio main-service-policy /config/minio-policy-main.json

echo ">>> Создаём пользователя основного сервиса..."
mc admin user add myminio "$MINIO_MAIN_USER" "$MINIO_MAIN_PASSWORD"

mc admin policy attach myminio main-service-policy --user "$MINIO_MAIN_USER"

echo ">>> Создаём политику для SAM..."
mc admin policy create myminio detection-service-policy /config/minio-policy-sam.json

echo ">>> Создаём пользователя для SAM..."
mc admin user add myminio "$MINIO_APP_SAM_USER" "$MINIO_APP_SAM_PASSWORD"
mc admin policy attach myminio detection-service-policy --user "$MINIO_APP_SAM_USER"

echo ">>> Создаём политику для YOLO..."
mc admin policy create myminio detection-service-yolo-policy /config/minio-policy-yolo.json

echo ">>> Создаём пользователя для YOLO..."
mc admin user add myminio "$MINIO_APP_YOLO_USER" "$MINIO_APP_YOLO_PASSWORD"
mc admin policy attach myminio detection-service-yolo-policy --user "$MINIO_APP_YOLO_USER"

echo ">>> Настраиваем lifecycle для output/..."
# Используем только базовые флаги, совместимые со всеми версиями
mc ilm add myminio/images \
  --prefix "output/" \
  --expire-days 1 \
  2>/dev/null && \
  echo ">>> Lifecycle: объекты в output/ удаляются через 24ч" || \
  echo "Не удалось настроить lifecycle (проверяем версию mc/MinIO)"

echo ">>> MinIO готов к работе!"

# Запуск
# docker-compose up -d minio minio-init
# для пересборки
# docker-compose down

# подключение
# docker-compose exec minio mc alias set myminio http://localhost:9000 miniouser admin123
# посмотреть все правила настроенные на minio
# docker-compose exec minio mc ilm rule list myminio/images
# Удалить лишнее правило
# docker-compose exec minio mc ilm rule remove myminio/images --id "d76fejg70ccjs9bl2fq0"