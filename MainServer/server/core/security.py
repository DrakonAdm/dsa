from cryptography.fernet import Fernet
import base64

from server.core.config import settings


_cipher = Fernet(settings.ANALYZE.TOKEN_SECRET.encode())

def generate_callback_token(task_id: str) -> str:
    encrypted = _cipher.encrypt(task_id.encode())
    return base64.urlsafe_b64encode(encrypted).decode().rstrip("=")

def verify_callback_token(token: str) -> str:
    # Fernet автоматически проверяет целостность и TTL (если настроен)
    try:
        padded = token + "=" * (4 - len(token) % 4)
        encrypted = base64.urlsafe_b64decode(padded)
        return _cipher.decrypt(encrypted).decode()
    except Exception:
        return None