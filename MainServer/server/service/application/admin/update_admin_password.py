from passlib.context import CryptContext
import os

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def update_password():
    new_password = input("Введите новый пароль администратора: ")
    hashed = pwd_context.hash(new_password)
    
    with open(".env", "r+") as f:
        lines = f.readlines()
        f.seek(0)
        for line in lines:
            if line.startswith("ADMIN_HASHED_PASSWORD="):
                f.write(f"ADMIN_HASHED_PASSWORD={hashed}\n")
            else:
                f.write(line)
        f.truncate()
    
    print("Пароль успешно обновлен!")