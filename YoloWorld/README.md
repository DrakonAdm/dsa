
**Установка и развертывание в образ**
***
Для сборки нужен будет cmake и по обстоятельствам Microsoft Visual Studio Build Tools 
и C++ build tools (при условии локальной сборкии .cpp файлов):
1. Для установки зависимостей необходимо выполнить команду:

    pip install -r requirements.txt


2. Код изменён в файле по пути:
./mmcv/transforms/loading.py
./anaconda3\envs\NeuralNetwork\Lib\site-packages\mmcv\transforms\loading.py
в метод transform() добавить в 92 строку перед filename = results['img_path'] код:

        if 'img' in results and results['img'] is not None:
            img = results['img']
            results['img'] = img
            results['img_shape'] = img.shape[:2]
            results['ori_shape'] = img.shape[:2]
            return results

    Для этого используется yolo_network/lib/pyproject.toml:

   pip install -e ./lib/mmcv/ -vv  
   pip install -e ./lib/mmyolo/ -vv


3. Далее необходимо установить в lib библиотеку yolo-worlds  

    Используется yolo_network/YOLOWorld/pyproject.toml для установки:  

    cd YOLOWorld
    pip install -e ./YOLOWorld/ -vv

3.5. Установить sahi:
```bash
pip install sahi==0.10.8 --no-deps
pip install fire click==8.0.4 pybboxes==0.1.6

```

4. Для установки в контейнере необходимо использовать:

   для Windows:

   compile/lib/mmcv_win/_ext.cp310-win_amd64.pyd

   для Linux:

   compile/lib/mmcv_linux/_ext.cpython-310-x86_64-linux-gnu.so

   Перенести нужный файл по пути:

   server/analyze/yolo_network/lib/mmcv/mmcv/

   при этом удалив .pyd/.so файл в этой директории.  

5. Для дополнительного улучшения кол-ва распознанных объектов можно использовать SAHI, для установки:  
    ```bash
    pip install sahi==0.11.36 --no-deps
    ```

6. После развёртывания для контейнера необходимо выделить >= 3 Гб ОЗУ, можно попробовать 
и меньше, при выделенной памяти в 2 Гб модель не загружается.  


7. Запустить: docker-compose up --build  

***

**Создание исполняемого файла**
***
1. При создании исполняемого файла (.exe) с помощью pyinstaller возможна внутрення ошибка в python=3.10, 
для исправления ошибки Python310\lib\dis.py в строке с «def _unpack_opargs» и внутри оператора else 
напишите новую строку со следующим текстом: «extended_arg = 0», затем сохраните файл.  


2. При создании исполняемого файла под Linux необходимо заменить .pyd файла на .so в дирректории mmcv и в my_app.spec  


3. Перейди в client/ и выполнить:  
    npm install
    npm run build  
  после этого полученную папку с файлами засунуть в папуку server


4. Добавить в конструктор сервера:  
    frontend_path = os.path.join(os.path.dirname(__file__), "dist")
    self.app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")  


5. В .spec файл добавить путь до собранной папки клиента в  
    Analysis( ..., datas = [
        ('server/dist',
        'server/dist'),
      ]
    )


6. Далее создать исполняемый файл через Pyistaller:
    pyinstaller my_app.spec


***
