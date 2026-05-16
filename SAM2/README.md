
**Установка и развертывание в образ**
***
Для сборки нужен будет cmake и по обстоятельствам Microsoft Visual Studio Build Tools 
и C++ build tools (при условии локальной сборкии .cpp файлов):
1. Для установки зависимостей необходимо выполнить команду:
```bash
    pip install -r requirements.txt
```

2. SAM2
```bash
cd ./Grounded-SAM-2
pip install -e .
```

3. Grounding Dino
```bash
cd ./Grounded-SAM-2/grounding_dino
pip install --no-build-isolation -e .
```