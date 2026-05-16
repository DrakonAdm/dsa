import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter, HTTPException, BackgroundTasks, Depends, Request

from server.config import settings
from server.schemas.request import DetectionRequest, DetectionResponse, QueueStatusResponse
from server.services.orchestrator_service import InferenceOrchestratorService
from server.services.task_manager import ModelVariant


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Загрузка моделей при старте, очистка при остановке."""
    print("Инициализация сервиса...")
    
    # Создаём оркестратор и сохраняем в state приложения
    orchestrator = InferenceOrchestratorService()
    app.state.orchestrator = orchestrator
    
    try:
        print("Loading shared YoloWorld model...")
        orchestrator._get_model(ModelVariant.YOLO_STANDARD)
        # print("Loading SAM2 wrappers...")
        # orchestrator._get_model(ModelVariant.SAM2_STANDARD)
    except Exception as e:
        print(f"Failed to preload models: {e}")
    
    yield
    
    print("Shutting down, cleaning up models...")
    await orchestrator.shutdown()
    print("Cleanup complete")


class MicroServerYolo:
    def __init__(self,):
        self.app = FastAPI(
            title="SegLabel AI Detection API",
            description="Сервис детекции YoloWorld",
            version="1.0.0",
            lifespan=lifespan,
        )
        # self.app = FastAPI(swagger_ui_parameters={"persistAuthorization": True})

        """Middleware"""
        origins = [
            "http://localhost:5173",  # Dev-сервер
            "http://192.168.0.85"
        ]
        # self.app.middleware("http")(self.auth_middleware)
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],  # Разрешает все методы (GET, POST и т.д.)
            allow_headers=["*"],  # Разрешает все заголовки
        )

        # self.app.add_middleware(SessionMiddleware, secret_key="secret-key")
        # self.app.add_middleware(
        #     SessionMiddleware,
        #     secret_key=os.getenv("SESSION_SECRET", "fallback-secret-key"),
        #     session_cookie="admin_session",
        #     https_only=True  # В продакшене должно быть True
        # )
        # self.app.add_middleware(TrustedHostMiddleware, allowed_hosts=["domain.com"])
        # self.app.add_middleware(HTTPSRedirectMiddleware)  # Для продакшена

        #prod
        # origins = [
        #     "http://localhost:5173",        # Dev-сервер
        # ]
        # self.app.add_middleware(
        #     CORSMiddleware,
        #     allow_origins=origins,
        #     allow_credentials=True,
        #     allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        #     allow_headers=[
        #         "Content-Type",
        #         "Authorization",
        #         "Accept",
        #         "X-Requested-With"
        #     ],
        #     expose_headers=["X-Total-Count"],  # Кастомные заголовки для фронтенда
        #     max_age=600,  # Кэшировать CORS-префлайт запросы на 10 минут
        # )

        self._register_routes()

    @staticmethod
    async def get_orchestrator(request: Request) -> InferenceOrchestratorService:
        return request.app.state.orchestrator
    
    def _register_routes(self):
        self._register_detect_routes()
        self._register_status_routes()

    def _register_detect_routes(self):
        router_detect = APIRouter(prefix='/api/v1/detect', tags=["detection"])

        @router_detect.post("/yoloworld", response_model=DetectionResponse)
        async def detect_yoloworld(
            request: DetectionRequest,
            background_tasks: BackgroundTasks,
            orchestrator: InferenceOrchestratorService = Depends(MicroServerYolo.get_orchestrator),
        ):
            """Детекция объектов YoloWorld (стандартная)."""
            # Проверяем доступность слота (быстрая проверка)
            if not orchestrator.acquire_model(ModelVariant.YOLO_STANDARD):
                raise HTTPException(
                    status_code=503,
                    detail={
                        "error": "service_busy",
                        "message": "Model slot is busy",
                        "retry_after_sec": 10,
                    }
                )            
            background_tasks.add_task(
                orchestrator.process_detection,
                image_path=request.image_path,
                texts=request.texts,
                variant=ModelVariant.YOLO_STANDARD,
                callback_url=request.callback_url,
                task_id=request.task_id,
            )
            
            return DetectionResponse(
                success=True,
                message=f"Task {request.image_path} queued for processing.",
                processing_time_ms=0,
            )

        @router_detect.post("/yoloworld-sahi", response_model=DetectionResponse)
        async def detect_yoloworld_sahi(
            request: DetectionRequest,
            background_tasks: BackgroundTasks,
            orchestrator: InferenceOrchestratorService = Depends(MicroServerYolo.get_orchestrator),
        ):
            """Детекция с SAHI slicing."""
            if not orchestrator.acquire_model(ModelVariant.YOLO_SAHI):
                raise HTTPException(
                    status_code=503,
                    detail={
                        "error": "service_busy",
                        "message": "Model slot is busy",
                        "retry_after_sec": 10,
                    }
                )            
            background_tasks.add_task(
                orchestrator.process_detection,
                image_path=request.image_path,
                texts=request.texts,
                variant=ModelVariant.YOLO_SAHI,
                callback_url=request.callback_url,
                task_id=request.task_id,
            )
            
            return DetectionResponse(
                success=True,
                message=f"Task {request.image_path} queued for processing.",
                processing_time_ms=0,
            )

        self.app.include_router(router_detect)

    def _register_status_routes(self):
        router_status = APIRouter(prefix='/api/status', tags=["status"])

        @router_status.get("/task", response_model=QueueStatusResponse)
        async def get_queue_status(
            orchestrator: InferenceOrchestratorService = Depends(MicroServerYolo.get_orchestrator),
        ):
            """Мониторинг статуса очередей."""
            return orchestrator.get_status()

        @router_status.get("/health")
        async def health_check():
            """Простая проверка доступности."""
            return {"status": "ok"}

        self.app.include_router(router_status)


if __name__ == "__main__":
    server = MicroServerYolo()
    app = server.app

    uvicorn.run(app, host=settings.API_HOST, port=settings.API_PORT, workers=1)


    """
    после сообщения на основной сервис данных и маски
    необходимо перенести маску в папку "upload/masks"
    """
