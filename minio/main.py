import io
import threading
import time
from pathlib import Path
from minio import Minio
from minio.error import S3Error
from PIL import Image

# Конфигурация
MINIO_ENDPOINT = "localhost:9000"
ACCESS_KEY = "miniouser"
SECRET_KEY = "admin123"
BUCKET_NAME = "test-images"
OBJECT_NAME = "test_image.jpg"
SECURE = False  # False для localhost, True для HTTPS

# Настройки вывода
SAVE_DOWNLOADED_IMAGES = True           # Сохранять скачанные изображения
DOWNLOAD_SAVE_DIR = Path("./output")  # Путь для сохранения
DISPLAY_DOWNLOADED_IMAGES = True       # Отображать изображения (откроется окно)

def create_minio_client():
    """Создаёт новый клиент MinIO."""
    return Minio(
        endpoint=MINIO_ENDPOINT,
        access_key=ACCESS_KEY,
        secret_key=SECRET_KEY,
        secure=SECURE,
    )

def ensure_bucket_exists(client, bucket_name):
    """Создаёт bucket, если он не существует."""
    if not client.bucket_exists(bucket_name):
        client.make_bucket(bucket_name)
        print(f"Bucket '{bucket_name}' создан")

def read_image_from_path(file_path: str | Path = "E:\\Project\\Analytic\\image\\test\\0035.jpg") -> tuple[io.BytesIO, str]:
    """Читает изображение из файла и возвращает байтовый поток + content-type."""
    path = Path(file_path)
    
    if not path.exists():
        raise FileNotFoundError(f"Файл не найден: {path}")
    
    content_types = {
        '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
        '.png': 'image/png', '.webp': 'image/webp',
        '.gif': 'image/gif', '.bmp': 'image/bmp',
    }
    content_type = content_types.get(path.suffix.lower(), 'application/octet-stream')
    
    with open(path, 'rb') as f:
        file_bytes = f.read()
    
    byte_stream = io.BytesIO(file_bytes)
    print(f"Прочитано изображение: {path.name} ({len(file_bytes)} байт, {content_type})")
    
    return byte_stream, content_type

def upload_image(client, bucket, object_name, image_data, content_type='image/jpeg'):
    """Загружает изображение в MinIO."""
    image_data.seek(0, 2)
    length = image_data.tell()
    image_data.seek(0)
    
    client.put_object(
        bucket_name=bucket,
        object_name=object_name,
        data=image_data,
        length=length,
        content_type=content_type,
    )
    print(f"Изображение '{object_name}' загружено ({length} байт)")

def process_downloaded_image(thread_id: int, data: bytes, content_type: str):
    """
    Обрабатывает скачанное изображение: сохраняет и/или отображает.
    Вызывается в потоке после успешного get_object().
    """
    try:
        # Сохранение на диск
        if SAVE_DOWNLOADED_IMAGES:
            DOWNLOAD_SAVE_DIR.mkdir(parents=True, exist_ok=True)
            
            # Уникальное имя: thread_0_test_image.jpg
            original_name = Path(OBJECT_NAME).stem
            ext = Path(OBJECT_NAME).suffix or '.jpg'
            save_path = DOWNLOAD_SAVE_DIR / f"thread_{thread_id}_{original_name}{ext}"
            
            with open(save_path, 'wb') as f:
                f.write(data)
            print(f"Поток {thread_id}: сохранено в {save_path}")
        
        # Отображение изображения
        if DISPLAY_DOWNLOADED_IMAGES:
            img = Image.open(io.BytesIO(data))
            print(f"Поток {thread_id}: отображение изображения {img.size} {img.mode}")
            img.show(title=f"Thread {thread_id} - {OBJECT_NAME}")
            # img.show() блокирует поток до закрытия окна изображения
            
    except Exception as e:
        print(f"Поток {thread_id}: ошибка обработки изображения: {e}")

def download_image_thread(thread_id, client, bucket, object_name, results, lock):
    """Поток для чтения изображения из MinIO с последующей обработкой."""
    try:
        start = time.time()
        
        response = client.get_object(bucket_name=bucket, object_name=object_name)
        data = response.read()
        content_type = response.headers.get('Content-Type', 'application/octet-stream')
        response.close()
        response.release_conn()  # Освобождаем соединение для reuse
        
        elapsed = time.time() - start
        
        # Обрабатываем изображение (сохранение/отображение)
        process_downloaded_image(thread_id, data, content_type)
        
        with lock:
            results[thread_id] = {
                'success': True,
                'size': len(data),
                'time_ms': elapsed * 1000,
                'thread': thread_id,
                'content_type': content_type
            }
        print(f"Поток {thread_id}: прочитано {len(data)} байт за {elapsed*1000:.1f} мс")
        
    except S3Error as e:
        with lock:
            results[thread_id] = {'success': False, 'error': str(e), 'thread': thread_id}
        print(f"Поток {thread_id}: ошибка MinIO: {e}")
    except Exception as e:
        with lock:
            results[thread_id] = {'success': False, 'error': str(e), 'thread': thread_id}
        print(f"Поток {thread_id}: ошибка: {e}")

def test_concurrent_read(num_threads=2):
    """Тестирует одновременное чтение одного объекта несколькими потоками."""
    print(f"\nТест конкурентного чтения ({num_threads} потоков)...")
    
    clients = [create_minio_client() for _ in range(num_threads)]
    results = {}
    lock = threading.Lock()
    threads = []
    
    for i, client in enumerate(clients):
        t = threading.Thread(
            target=download_image_thread,
            args=(i, client, BUCKET_NAME, OBJECT_NAME, results, lock)
        )
        threads.append(t)
        t.start()
    
    for t in threads:
        t.join()
    
    successful = sum(1 for r in results.values() if r.get('success'))
    print(f"\nРезультаты: {successful}/{num_threads} успешных чтений")
    
    if successful == num_threads:
        times = [r['time_ms'] for r in results.values()]
        print(f"Среднее время: {sum(times)/len(times):.1f} мс")
        print(f"Мин/Макс: {min(times):.1f} / {max(times):.1f} мс")
        print(f"Проверьте папку: {DOWNLOAD_SAVE_DIR.absolute()}")
    
    return successful == num_threads

def main():
    print("MinIO Concurrent Access Test + Image Output")
    print("=" * 60)
    
    client = create_minio_client()
    
    try:
        # 1. Создаём bucket
        ensure_bucket_exists(client, BUCKET_NAME)
        
        # 2. Загружаем тестовое изображение
        print("\nЗагрузка тестового изображения...")
        image_data, content_type = read_image_from_path()
        upload_image(client, BUCKET_NAME, OBJECT_NAME, image_data, content_type)
        
        # 3. Тестируем конкурентное чтение с сохранением/отображением
        success = test_concurrent_read(num_threads=2)
        
        # 4. Тест с повышенной нагрузкой
        if success:
            print("\n" + "=" * 60)
            test_concurrent_read(num_threads=5)
        
        # 5. Presigned URL для доступа с других серверов
        print(f"\nPresigned URL для доступа извне (7 дней):")
        url = client.presigned_get_object(
            bucket_name=BUCKET_NAME,
            object_name=OBJECT_NAME,
        )
        print(f"   {url}")
        print("   → Можно использовать с любого сервера без credentials")
        
    except S3Error as e:
        print(f"Ошибка MinIO: {e}")
    except FileNotFoundError as e:
        print(f"{e}")
        print("Укажите корректный путь в read_image_from_path()")
    except Exception as e:
        print(f"Ошибка: {type(e).__name__}: {e}")
    finally:
        print("\nТест завершён")

if __name__ == "__main__":
    main()
