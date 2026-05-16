import logging
import os

from server.core.config import BASE_DIR


class Logger:
    def __init__(self, log_file=f"{BASE_DIR}/log/app.log"):
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        self.log_file = log_file
        self._configure_logging()

    def _configure_logging(self):
        file_handler = logging.FileHandler(self.log_file, encoding="utf-8")
        stream_handler = logging.StreamHandler()

        LEVEL = logging.DEBUG
        LEVEL_LOG_LIB = logging.INFO

        logging.basicConfig(
            level=LEVEL,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[file_handler, stream_handler]
        )

        for lib in ["aiortc", "asyncio", "matplotlib", "PIL", "urllib3", "rasterio", "websockets"]:
            logging.getLogger(lib).setLevel(LEVEL_LOG_LIB)

    def class_log(self, class_name: str):
        class ClassSpecificLogger:
            def __init__(self, class_name, parent_logger):
                self.class_name = class_name
                self.logger = logging.getLogger(class_name)
                self.parent_logger = parent_logger  # Сохраняем ссылку на родительский логгер

            def get_info(self, message):
                self._log('info', message)

            def get_error(self, message):
                self._log('error', message)

            def get_debug(self, message):
                self._log('debug', message)

            def get_warning(self, message):
                self._log('warning', message)

            def _log(self, level, message):
                old_factory = logging.getLogRecordFactory()
                
                def record_factory(*args, **kwargs):
                    record = old_factory(*args, **kwargs)
                    record.caller = self.class_name
                    return record
                
                logging.setLogRecordFactory(record_factory)
                try:
                    getattr(self.logger, level)(message)
                finally:
                    logging.setLogRecordFactory(old_factory)

            def get_logger(self, name):
                return logging.getLogger(name)

            def class_log(self, class_name: str):
                # Делегируем вызов родительскому логгеру
                return self.parent_logger.class_log(class_name)

        return ClassSpecificLogger(class_name, self)
