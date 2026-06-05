import { type ChangeEvent, useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import PageTransition from '../components/PageTransition';
import WorkspaceCanvas, {
  type ActiveToolMode,
  type AnnotationObject,
  type OpacityTargetMode,
  type WorkspaceModelItem
} from '../components/WorkspaceCanvas';
import {
  api,
  type AnalysisSocketMessage,
  type AnnotationPayload,
  type AnnotationResponse,
  type ClassType,
  type ImageUploadMetadata,
  type ModelConfig,
  type Project
} from '../lib/api';

interface ClassItem {
  name: string;
  source: 'imported' | 'manual' | 'model';
  color: string;
  visible: boolean;
  opacity?: number;
}

interface WorkspaceImage {
  id: number | string;
  name: string;
  src: string;
  annotations: AnnotationObject[];
}

interface WorkspaceState {
  projectName: string;
  taskName: string;
  images: WorkspaceImage[];
  currentImageIndex: number;
  selectedObjectId: AnnotationObject['id'] | null;
  classList: ClassItem[];
  activeTool: ActiveToolMode;
  activeLabel: string;
  maskOpacity: number;
  selectedSegmentationModels: string[];
  selectedDetectionModels: string[];
}

interface CocoImage {
  id: number | string;
  file_name: string;
  width?: number;
  height?: number;
}

interface CocoAnnotation {
  image_id: number | string;
  category_id?: number | string;
  bbox?: number[];
  segmentation?: unknown;
}

interface CocoCategory {
  id: number | string;
  name: string;
}

interface CocoDataset {
  images?: CocoImage[];
  annotations?: CocoAnnotation[];
  categories?: CocoCategory[];
}

const STORAGE_KEY = 'seglabel-ai.workspace';

const EMPTY_IMAGE_ID = 'empty';
const EMPTY_WORKSPACE_IMAGE: WorkspaceImage = {
  id: EMPTY_IMAGE_ID,
  name: 'Нет изображения',
  src: '',
  annotations: []
};

const cloneState = <T,>(value: T): T => JSON.parse(JSON.stringify(value));

const getObjectSourceKey = (object: AnnotationObject) => {
  if (object.source === 'model') {
    return object.modelName ?? 'Model';
  }

  if (object.source === 'imported') {
    return 'Imported';
  }

  return 'Manual';
};

const isUuid = (value: AnnotationObject['id']): value is string =>
  typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);

const createLocalAnnotationId = () => `local-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

const getAnnotationApiType = (object: Pick<AnnotationObject, 'type'>): AnnotationPayload['type'] =>
  object.type === 'box' ? 'detect' : 'segment';

const serializeAnnotationObject = (object: AnnotationObject): AnnotationPayload => {
  const className = object.label.trim();
  const data =
    object.type === 'box' && object.area
      ? [object.area.x, object.area.y, object.area.x + object.area.width, object.area.y + object.area.height]
      : object.points?.map((point) => [point.x, point.y]) ?? [];

  return {
    type: getAnnotationApiType(object),
    class_name: className,
    data
  };
};

const normalizeBackendType = (type: AnnotationResponse['type']) =>
  type === 'detect' ? 'detection' : type === 'segment' ? 'segmentation' : type;

const isNumberArray = (value: unknown): value is number[] => Array.isArray(value) && value.every((item) => typeof item === 'number');

const isPointArray = (value: unknown): value is Array<[number, number]> =>
  Array.isArray(value) &&
  value.every((item) => Array.isArray(item) && item.length >= 2 && typeof item[0] === 'number' && typeof item[1] === 'number');

const getPointsBounds = (points: Array<{ x: number; y: number }>) => {
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);

  return {
    x: Math.min(...xs),
    y: Math.min(...ys),
    width: Math.max(...xs) - Math.min(...xs),
    height: Math.max(...ys) - Math.min(...ys)
  };
};

const annotationFromApi = (annotation: AnnotationResponse): AnnotationObject => {
  const backendType = normalizeBackendType(annotation.type);
  const data = annotation.data;

  if (isNumberArray(data) && data.length >= 4) {
    return {
      id: annotation.id,
      label: annotation.class_name,
      color: '#7CFC8A',
      type: 'box',
      source: 'manual',
      area: {
        x: data[0],
        y: data[1],
        width: data[2] - data[0],
        height: data[3] - data[1]
      }
    };
  }

  if (isPointArray(data)) {
    const points = data.map(([x, y]) => ({ x, y }));

    return {
      id: annotation.id,
      label: annotation.class_name,
      color: '#7CFC8A',
      type: backendType === 'detection' ? 'box' : 'polygon',
      source: 'manual',
      points,
      area: points.length ? getPointsBounds(points) : undefined
    };
  }

  const dataRecord = data && typeof data === 'object' && !Array.isArray(data) ? (data as Record<string, unknown>) : null;
  const objectData = (
    dataRecord?.object && typeof dataRecord.object === 'object' ? dataRecord.object : dataRecord ?? {}
  ) as Partial<AnnotationObject>;

  return {
    id: annotation.id,
    label: annotation.class_name,
    color: objectData.color ?? '#7CFC8A',
    type: objectData.type ?? (backendType === 'detection' ? 'box' : 'polygon'),
    source: objectData.source ?? 'manual',
    operation: objectData.operation,
    modelName: objectData.modelName,
    score: objectData.score,
    opacity: objectData.opacity,
    locked: objectData.locked,
    area: objectData.area,
    points: objectData.points
  };
};

const annotationsFromRecord = (annotations: Record<string, AnnotationResponse> | undefined) =>
  Object.values(annotations ?? {}).map(annotationFromApi);

const mergeAnnotationObjects = (primary: AnnotationObject[], fallback: AnnotationObject[]) => {
  const byId = new Map<AnnotationObject['id'], AnnotationObject>();

  [...fallback, ...primary].forEach((annotation) => {
    byId.set(annotation.id, annotation);
  });

  return Array.from(byId.values());
};

const classItemFromApi = (classType: ClassType): ClassItem => ({
  name: classType.name_eng || classType.name_ru,
  source: 'imported',
  color: '#7CFC8A',
  visible: true
});

const getFileFormat = (fileName: string) => fileName.split('.').pop()?.toLowerCase() || null;

const normalizeCocoFileName = (name: string) => name.replace(/\\/g, '/').split('/').pop()?.toLowerCase() ?? name.toLowerCase();

const segmentationToPoints = (segmentation: unknown) => {
  if (!Array.isArray(segmentation)) {
    return null;
  }

  const rawPolygon = Array.isArray(segmentation[0])
    ? segmentation.find((item): item is number[] => Array.isArray(item) && item.every((value) => typeof value === 'number'))
    : segmentation.every((value) => typeof value === 'number')
      ? (segmentation as number[])
      : null;

  if (!rawPolygon || rawPolygon.length < 6) {
    return null;
  }

  const points: Array<[number, number]> = [];
  for (let index = 0; index < rawPolygon.length - 1; index += 2) {
    points.push([rawPolygon[index], rawPolygon[index + 1]]);
  }

  return points.length >= 3 ? points : null;
};

const buildCocoUploadMetadata = async (cocoFile: File, imageFiles: File[]): Promise<ImageUploadMetadata[]> => {
  const dataset = JSON.parse(await cocoFile.text()) as CocoDataset;
  const cocoImages = Array.isArray(dataset.images) ? dataset.images : [];
  const cocoAnnotations = Array.isArray(dataset.annotations) ? dataset.annotations : [];
  const cocoCategories = Array.isArray(dataset.categories) ? dataset.categories : [];
  const categoryNameById = new Map(cocoCategories.map((category) => [String(category.id), category.name || 'Object']));
  const imageByFileName = new Map(cocoImages.map((image) => [normalizeCocoFileName(image.file_name), image]));
  const annotationsByImageId = new Map<string, CocoAnnotation[]>();

  cocoAnnotations.forEach((annotation) => {
    const key = String(annotation.image_id);
    annotationsByImageId.set(key, [...(annotationsByImageId.get(key) ?? []), annotation]);
  });

  return imageFiles.map((file) => {
    const cocoImage = imageByFileName.get(normalizeCocoFileName(file.name));
    const annotations = (cocoImage ? annotationsByImageId.get(String(cocoImage.id)) ?? [] : []).flatMap<AnnotationPayload>((annotation) => {
      const className = categoryNameById.get(String(annotation.category_id)) ?? 'Object';
      const points = segmentationToPoints(annotation.segmentation);

      if (points) {
        return [{ type: 'segment', class_name: className, data: points }];
      }

      if (Array.isArray(annotation.bbox) && annotation.bbox.length >= 4) {
        const [x, y, width, height] = annotation.bbox;
        return [{ type: 'detect', class_name: className, data: [x, y, x + width, y + height] }];
      }

      return [];
    });

    return {
      width: cocoImage?.width ?? null,
      height: cocoImage?.height ?? null,
      format: getFileFormat(file.name),
      annotations,
      masks: []
    };
  });
};

const buildInitialState = (): WorkspaceState => ({
  projectName: 'Проект',
  taskName: 'Нет изображения',
  images: [EMPTY_WORKSPACE_IMAGE],
  currentImageIndex: 0,
  selectedObjectId: null,
  classList: [],
  activeTool: null,
  activeLabel: '',
  maskOpacity: 0.58,
  selectedSegmentationModels: [],
  selectedDetectionModels: []
});

const WorkspacePage = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const initialState = useMemo(buildInitialState, []);
  const [workspace, setWorkspace] = useState<WorkspaceState>(initialState);
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState('');
  const [availableModels, setAvailableModels] = useState<ModelConfig[]>([]);
  const [availableClasses, setAvailableClasses] = useState<ClassType[]>([]);
  const [isRunningModels, setIsRunningModels] = useState(false);
  const [isLoadingRemoteImages, setIsLoadingRemoteImages] = useState(false);
  const [newClassName, setNewClassName] = useState('');
  const [statusMessage, setStatusMessage] = useState('Готово к разметке');
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [hasSavedDraft, setHasSavedDraft] = useState<boolean>(() => Boolean(localStorage.getItem(STORAGE_KEY)));
  const [opacityTargetMode, setOpacityTargetMode] = useState<OpacityTargetMode>('class');
  const [opacityClassName, setOpacityClassName] = useState(initialState.activeLabel);
  const [analysisClassNames, setAnalysisClassNames] = useState<string[]>([]);
  const [history, setHistory] = useState<WorkspaceState[]>([cloneState(initialState)]);
  const [historyIndex, setHistoryIndex] = useState(0);
  const historyRef = useRef<WorkspaceState[]>([cloneState(initialState)]);
  const historyIndexRef = useRef(0);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const uploadedUrlsRef = useRef<string[]>([]);

  const currentImage = workspace.images[workspace.currentImageIndex] ?? EMPTY_WORKSPACE_IMAGE;
  const objects = currentImage?.annotations ?? [];
  const canPersistAnnotations = Boolean(selectedProjectId && currentImage && isUuid(currentImage.id));

  const hiddenLabels = useMemo(
    () => workspace.classList.filter((item) => !item.visible).map((item) => item.name),
    [workspace.classList]
  );

  useEffect(() => {
    if (workspace.classList.some((item) => item.name === opacityClassName)) {
      return;
    }

    setOpacityClassName(workspace.activeLabel || workspace.classList[0]?.name || '');
  }, [opacityClassName, workspace.activeLabel, workspace.classList]);

  useEffect(() => {
    const classNames = new Set(workspace.classList.map((item) => item.name));

    setAnalysisClassNames((current) => {
      const validCurrent = current.filter((name) => classNames.has(name));

      if (validCurrent.length || current.length === 0) {
        return validCurrent;
      }

      const fallback = workspace.activeLabel || workspace.classList[0]?.name;
      return fallback ? [fallback] : [];
    });
  }, [workspace.activeLabel, workspace.classList]);

  const segmentationModels = useMemo<WorkspaceModelItem[]>(
    () => availableModels.filter((model) => model.type.includes('segmentation')),
    [availableModels]
  );
  const detectionModels = useMemo<WorkspaceModelItem[]>(
    () => availableModels.filter((model) => model.type.includes('detection')),
    [availableModels]
  );
  const selectedModelIds = useMemo(
    () =>
      availableModels
        .filter((model) => [...workspace.selectedSegmentationModels, ...workspace.selectedDetectionModels].includes(String(model.id)))
        .map((model) => model.id),
    [availableModels, workspace.selectedDetectionModels, workspace.selectedSegmentationModels]
  );

  useEffect(() => {
    return () => {
      uploadedUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
    };
  }, []);

  useEffect(() => {
    api
      .listProjects()
      .then((items) => {
        setProjects(items);
        setSelectedProjectId(projectId ?? items[0]?.id ?? '');
      })
      .catch((err) => setStatusMessage(err instanceof Error ? err.message : 'Не удалось загрузить проекты'));
  }, [projectId]);

  useEffect(() => {
    if (!selectedProjectId) {
      return;
    }

    const project = projects.find((item) => item.id === selectedProjectId);
    let isCancelled = false;
    setIsLoadingRemoteImages(true);
    setStatusMessage('Загружаем изображения проекта...');

    api
      .getProjectImages(selectedProjectId)
      .then(async (items) => {
        const [projectClasses, projectModels] = await Promise.all([
          api.getProjectClasses(selectedProjectId).catch(() => [] as ClassType[]),
          api.getProjectModels(selectedProjectId).catch(() => [] as ModelConfig[])
        ]);
        const remoteImages = await Promise.all(
          items.map(async (item, index) => {
            const src = await api.getImageObjectUrl(selectedProjectId, item.id);
            const embeddedAnnotations = annotationsFromRecord(item.annotations);
            const fetchedAnnotations = await api
              .getAnnotations(selectedProjectId, item.id)
              .then((annotations) => annotations.map(annotationFromApi))
              .catch(() => [] as AnnotationObject[]);
            uploadedUrlsRef.current.push(src);

            return {
              id: item.id,
              name: item.file_path?.split('/').pop() ?? `${index + 1}.${item.format ?? 'jpg'}`,
              src,
              annotations: mergeAnnotationObjects(fetchedAnnotations, embeddedAnnotations)
            } satisfies WorkspaceImage;
          })
        );

        if (isCancelled) {
          remoteImages.forEach((image) => URL.revokeObjectURL(image.src));
          return;
        }

        const classList = [
          ...projectClasses.map(classItemFromApi),
          ...Array.from(new Set(remoteImages.flatMap((image) => image.annotations.map((item) => item.label))))
            .filter((name) => !projectClasses.some((classType) => classType.name_eng === name || classType.name_ru === name))
            .map<ClassItem>((name) => ({
              name,
              source: 'imported',
              color: '#7CFC8A',
              visible: true
            }))
        ];
        const activeLabel =
          remoteImages[0]?.annotations[0]?.label ?? projectClasses[0]?.name_eng ?? projectClasses[0]?.name_ru ?? '';
        const defaultModel = projectModels.find((model) => model.type.includes('segmentation') || model.type.includes('detection'));

        const nextState: WorkspaceState = {
          ...buildInitialState(),
          projectName: project?.name ?? 'Проект',
          taskName: remoteImages[0]?.name.replace(/\.[^.]+$/, '') ?? 'Нет изображений',
          images: remoteImages.length ? remoteImages : [EMPTY_WORKSPACE_IMAGE],
          currentImageIndex: 0,
          selectedObjectId: null,
          classList,
          activeLabel,
          selectedSegmentationModels: defaultModel?.type.includes('segmentation') ? [String(defaultModel.id)] : [],
          selectedDetectionModels: defaultModel?.type.includes('detection') ? [String(defaultModel.id)] : []
        };

        historyRef.current = [cloneState(nextState)];
        historyIndexRef.current = 0;
        setHistory(historyRef.current);
        setHistoryIndex(0);
        setAvailableModels(projectModels);
        setAvailableClasses(projectClasses);
        setWorkspace(nextState);
        setStatusMessage(remoteImages.length ? `Загружено изображений проекта: ${remoteImages.length}` : 'В проекте пока нет изображений');
      })
      .catch((err) => setStatusMessage(err instanceof Error ? err.message : 'Не удалось загрузить изображения проекта'))
      .finally(() => {
        if (!isCancelled) {
          setIsLoadingRemoteImages(false);
        }
      });

    return () => {
      isCancelled = true;
    };
  }, [projects, selectedProjectId]);

  const pushHistory = (nextState: WorkspaceState) => {
    const snapshot = cloneState(nextState);
    const nextHistory = [...historyRef.current.slice(0, historyIndexRef.current + 1), snapshot];
    historyRef.current = nextHistory;
    historyIndexRef.current = nextHistory.length - 1;
    setHistory(nextHistory);
    setHistoryIndex(historyIndexRef.current);
  };

  const updateWorkspace = (
    updater: (current: WorkspaceState) => WorkspaceState,
    options?: { recordHistory?: boolean; status?: string }
  ) => {
    setWorkspace((current) => {
      const next = updater(current);

      if (options?.recordHistory !== false) {
        pushHistory(next);
      }

      return next;
    });

    if (options?.status) {
      setStatusMessage(options.status);
    }
  };

  const replaceWorkspace = (nextState: WorkspaceState, status: string, recordHistory = true) => {
    setWorkspace(nextState);

    if (recordHistory) {
      pushHistory(nextState);
    }

    setStatusMessage(status);
  };

  const setCurrentImageIndex = (nextIndex: number) => {
    updateWorkspace(
      (current) => ({
        ...current,
        currentImageIndex: Math.max(0, Math.min(nextIndex, current.images.length - 1)),
        selectedObjectId: null
      }),
      { recordHistory: false, status: `Открыто изображение ${Math.max(1, Math.min(nextIndex + 1, workspace.images.length))}` }
    );
  };

  const handleUndo = () => {
    if (historyIndexRef.current === 0) {
      setStatusMessage('Больше нечего отменять');
      return;
    }

    const nextIndex = historyIndexRef.current - 1;
    historyIndexRef.current = nextIndex;
    setHistoryIndex(nextIndex);
    setWorkspace(cloneState(historyRef.current[nextIndex]));
    setStatusMessage('Последнее действие отменено');
  };

  const handleRedo = () => {
    if (historyIndexRef.current >= historyRef.current.length - 1) {
      setStatusMessage('Больше нечего повторять');
      return;
    }

    const nextIndex = historyIndexRef.current + 1;
    historyIndexRef.current = nextIndex;
    setHistoryIndex(nextIndex);
    setWorkspace(cloneState(historyRef.current[nextIndex]));
    setStatusMessage('Действие повторено');
  };

  const handleSave = () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(cloneState(workspace)));
    setHasSavedDraft(true);
    setStatusMessage(`Черновик сохранён: ${new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}`);
  };

  const handleLoadSaved = () => {
    const raw = localStorage.getItem(STORAGE_KEY);

    if (!raw) {
      setStatusMessage('Сохранённый черновик не найден');
      return;
    }

    const saved = JSON.parse(raw) as WorkspaceState;
    replaceWorkspace(saved, 'Черновик загружен');
    setIsMenuOpen(false);
  };

  const handleExportProject = () => {
    const blob = new Blob(
      [
        JSON.stringify(
          {
            projectName: workspace.projectName,
            taskName: workspace.taskName,
            images: workspace.images.map((image) => ({
              name: image.name,
              annotations: image.annotations
            })),
            classList: workspace.classList,
            selectedSegmentationModels: workspace.selectedSegmentationModels,
            selectedDetectionModels: workspace.selectedDetectionModels
          },
          null,
          2
        )
      ],
      { type: 'application/json' }
    );
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${workspace.projectName.replace(/\s+/g, '-').toLowerCase() || 'seglabel-project'}.json`;
    link.click();
    URL.revokeObjectURL(url);
    setStatusMessage('Проект экспортирован в JSON');
  };

  const handleImageUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);

    if (!files.length) {
      return;
    }

    const cocoFile = files.find((file) => file.name.toLowerCase().endsWith('.json'));
    const imageFiles = files.filter((file) => file.type.startsWith('image/'));

    if (imageFiles.length === 0) {
      setStatusMessage(cocoFile ? 'Выберите COCO JSON вместе с файлами изображений' : 'Выберите файлы изображений');
      event.target.value = '';
      return;
    }

    if (selectedProjectId) {
      setIsLoadingRemoteImages(true);
      setStatusMessage(cocoFile ? `Загружаем COCO dataset в backend: ${imageFiles.length}` : `Загружаем изображений в backend: ${imageFiles.length}`);

      try {
        const metadata = cocoFile ? await buildCocoUploadMetadata(cocoFile, imageFiles) : undefined;
        const uploaded = await api.uploadImages(selectedProjectId, imageFiles, metadata ? { metadata } : undefined);
        const remoteImages = await Promise.all(
          uploaded.map(async (item, index) => {
            const src = await api.getImageObjectUrl(selectedProjectId, item.id);
            const fetchedAnnotations = await api
              .getAnnotations(selectedProjectId, item.id)
              .then((annotations) => annotations.map(annotationFromApi))
              .catch(() => [] as AnnotationObject[]);
            uploadedUrlsRef.current.push(src);

            return {
              id: item.id,
              name: item.file_path?.split('/').pop() ?? imageFiles[index]?.name ?? `${index + 1}.${item.format ?? 'jpg'}`,
              src,
              annotations: mergeAnnotationObjects(fetchedAnnotations, annotationsFromRecord(item.annotations))
            } satisfies WorkspaceImage;
          })
        );
        const refreshedClasses = cocoFile ? await api.getProjectClasses(selectedProjectId).catch(() => availableClasses) : availableClasses;
        const uploadedClassNames = Array.from(new Set(remoteImages.flatMap((image) => image.annotations.map((item) => item.label))));

        updateWorkspace(
          (current) => {
            const existingImages = current.images.filter((image) => image.id !== EMPTY_IMAGE_ID);
            const existingClassNames = new Set(current.classList.map((item) => item.name.toLowerCase()));
            const refreshedClassItems = refreshedClasses
              .map(classItemFromApi)
              .filter((item) => !existingClassNames.has(item.name.toLowerCase()));
            const refreshedClassNames = new Set([
              ...current.classList.map((item) => item.name.toLowerCase()),
              ...refreshedClassItems.map((item) => item.name.toLowerCase())
            ]);
            const annotationClassItems = uploadedClassNames
              .filter((name) => !refreshedClassNames.has(name.toLowerCase()))
              .map<ClassItem>((name) => ({ name, source: 'imported', color: '#7CFC8A', visible: true }));

            return {
              ...current,
              images: [...existingImages, ...remoteImages],
              currentImageIndex: existingImages.length,
              taskName: imageFiles[0]?.name.replace(/\.[^.]+$/, '') ?? current.taskName,
              selectedObjectId: null,
              classList: [...current.classList, ...refreshedClassItems, ...annotationClassItems],
              activeLabel: current.activeLabel || refreshedClassItems[0]?.name || annotationClassItems[0]?.name || ''
            };
          },
          { status: cocoFile ? `Backend загрузил COCO dataset: ${remoteImages.length}` : `Backend загрузил изображений: ${remoteImages.length}` }
        );
        setAvailableClasses(refreshedClasses);
      } catch (err) {
        setStatusMessage(err instanceof Error ? `Не удалось загрузить dataset в backend: ${err.message}` : 'Не удалось загрузить dataset в backend');
      } finally {
        setIsLoadingRemoteImages(false);
        event.target.value = '';
      }

      return;
    }

    const nextImages: WorkspaceImage[] = imageFiles.map((file, index) => {
      const src = URL.createObjectURL(file);
      uploadedUrlsRef.current.push(src);

      return {
        id: Date.now() + index,
        name: file.name,
        src,
        annotations: []
      };
    });
    const localMetadata = cocoFile ? await buildCocoUploadMetadata(cocoFile, imageFiles).catch(() => null) : null;
    const annotatedNextImages = localMetadata
      ? nextImages.map((image, index) => ({
          ...image,
          annotations: localMetadata[index].annotations.map((annotation) => annotationFromApi({
            id: createLocalAnnotationId(),
            type: annotation.type,
            class_name: annotation.class_name,
            data: annotation.data
          } satisfies AnnotationResponse))
        }))
      : nextImages;

    updateWorkspace(
      (current) => {
        const existingImages = current.images.filter((image) => image.id !== EMPTY_IMAGE_ID);
        const importedClassNames = Array.from(new Set(annotatedNextImages.flatMap((image) => image.annotations.map((item) => item.label))));
        const existingClassNames = new Set(current.classList.map((item) => item.name.toLowerCase()));
        const importedClassItems = importedClassNames
          .filter((name) => !existingClassNames.has(name.toLowerCase()))
          .map<ClassItem>((name) => ({ name, source: 'imported', color: '#7CFC8A', visible: true }));

        return {
          ...current,
          images: [...existingImages, ...annotatedNextImages],
          currentImageIndex: existingImages.length,
          taskName: imageFiles[0]?.name.replace(/\.[^.]+$/, '') ?? current.taskName,
          selectedObjectId: null,
          classList: [...current.classList, ...importedClassItems],
          activeLabel: current.activeLabel || importedClassItems[0]?.name || ''
        };
      },
      { status: cocoFile ? `Добавлен локальный COCO dataset: ${annotatedNextImages.length}` : `Добавлено изображений: ${imageFiles.length}` }
    );

    event.target.value = '';
  };

  const replaceAnnotationId = (imageId: WorkspaceImage['id'], localId: AnnotationObject['id'], remote: AnnotationResponse) => {
    const remoteObject = annotationFromApi(remote);

    updateWorkspace(
      (current) => ({
        ...current,
        images: current.images.map((image) =>
          image.id === imageId
            ? {
                ...image,
                annotations: image.annotations.map((item) => (item.id === localId ? remoteObject : item))
              }
            : image
        ),
        selectedObjectId: current.selectedObjectId === localId ? remoteObject.id : current.selectedObjectId
      }),
      { recordHistory: false }
    );
  };

  const ensureRemoteClass = async (projectId: string, label: string) => {
    const exists =
      availableClasses.some((item) => item.name_eng.toLowerCase() === label.toLowerCase() || item.name_ru.toLowerCase() === label.toLowerCase()) ||
      workspace.classList.some((item) => item.name.toLowerCase() === label.toLowerCase() && item.source !== 'manual');

    if (exists) {
      return;
    }

    try {
      const createdClass = await api.createProjectClass(projectId, label);
      const classItem = classItemFromApi(createdClass);

      setAvailableClasses((current) => (current.some((item) => item.id === createdClass.id) ? current : [...current, createdClass]));
      updateWorkspace(
        (current) => ({
          ...current,
          classList: current.classList.some((item) => item.name.toLowerCase() === classItem.name.toLowerCase())
            ? current.classList.map((item) => (item.name.toLowerCase() === classItem.name.toLowerCase() ? { ...item, source: 'imported' } : item))
            : [...current.classList, classItem]
        }),
        { recordHistory: false }
      );
    } catch (err) {
      if (!(err instanceof Error) || !err.message.includes('уже существует')) {
        throw err;
      }

      const refreshedClasses = await api.getProjectClasses(projectId);
      setAvailableClasses(refreshedClasses);
    }
  };

  const removeLocalAnnotation = (imageId: WorkspaceImage['id'], objectId: AnnotationObject['id']) => {
    updateWorkspace(
      (current) => ({
        ...current,
        images: current.images.map((image) =>
          image.id === imageId
            ? {
                ...image,
                annotations: image.annotations.filter((item) => item.id !== objectId)
              }
            : image
        ),
        selectedObjectId: current.selectedObjectId === objectId ? null : current.selectedObjectId
      }),
      { recordHistory: false }
    );
  };

  const createObject = (object: Omit<AnnotationObject, 'id'>) => {
    if (!object.label.trim()) {
      setStatusMessage('Сначала добавьте и выберите класс');
      return;
    }

    const imageForRequest = currentImage;
    const localId = createLocalAnnotationId();
    const shouldPersist = Boolean(selectedProjectId && imageForRequest && isUuid(imageForRequest.id));
    const nextObject: AnnotationObject = { ...object, id: localId };

    updateWorkspace(
      (current) => {
        const images = current.images.map((image, index) =>
          index === current.currentImageIndex
            ? { ...image, annotations: [...image.annotations, nextObject] }
            : image
        );
        const hasClass = current.classList.some((item) => item.name === object.label);

        return {
          ...current,
          images,
          selectedObjectId: nextObject.id,
          classList: hasClass
            ? current.classList
            : [...current.classList, { name: object.label, source: 'manual', color: object.color, visible: true }]
        };
      },
      { status: `Создан объект ${object.label}` }
    );

    if (shouldPersist) {
      ensureRemoteClass(selectedProjectId, object.label)
        .then(() => api.createAnnotation(selectedProjectId, String(imageForRequest.id), serializeAnnotationObject(nextObject)))
        .then((remote) => {
          replaceAnnotationId(imageForRequest.id, localId, remote);
          setStatusMessage(`Объект ${object.label} сохранён в БД`);
        })
        .catch((err) => {
          removeLocalAnnotation(imageForRequest.id, localId);
          setStatusMessage(err instanceof Error ? `Не удалось сохранить объект: ${err.message}` : 'Не удалось сохранить объект');
        });
    }
  };

  const updateObject = (id: AnnotationObject['id'], patch: Partial<AnnotationObject>) => {
    const imageForRequest = currentImage;
    const target = imageForRequest?.annotations.find((item) => item.id === id);
    const nextObject = target ? { ...target, ...patch } : null;

    updateWorkspace(
      (current) => ({
        ...current,
        images: current.images.map((image, index) =>
          index === current.currentImageIndex
            ? {
                ...image,
                annotations: image.annotations.map((item) => (item.id === id ? { ...item, ...patch } : item))
              }
            : image
        )
      }),
      { status: `Объект ${id} обновлён` }
    );

    if (selectedProjectId && imageForRequest && isUuid(imageForRequest.id) && isUuid(id) && nextObject) {
      api
        .updateAnnotation(selectedProjectId, imageForRequest.id, id, serializeAnnotationObject(nextObject))
        .then(() => setStatusMessage(`Объект ${id} обновлён в БД`))
        .catch((err) => setStatusMessage(err instanceof Error ? `Не удалось обновить объект: ${err.message}` : 'Не удалось обновить объект'));
    }
  };

  const deleteObject = (id: AnnotationObject['id']) => {
    const imageForRequest = currentImage;

    updateWorkspace(
      (current) => ({
        ...current,
        images: current.images.map((image, index) =>
          index === current.currentImageIndex
            ? {
                ...image,
                annotations: image.annotations.filter((item) => item.id !== id)
              }
            : image
        ),
        selectedObjectId: current.selectedObjectId === id ? null : current.selectedObjectId
      }),
      { status: `Объект ${id} удалён` }
    );

    if (selectedProjectId && imageForRequest && isUuid(imageForRequest.id) && isUuid(id)) {
      api
        .deleteAnnotation(selectedProjectId, imageForRequest.id, id)
        .then(() => setStatusMessage(`Объект ${id} удалён из БД`))
        .catch((err) => setStatusMessage(err instanceof Error ? `Не удалось удалить объект: ${err.message}` : 'Не удалось удалить объект'));
    }
  };

  const splitObject = (id: AnnotationObject['id'], splitX: number) => {
    const imageForRequest = currentImage;
    let splitObjects: AnnotationObject[] = [];

    updateWorkspace(
      (current) => {
        const currentImage = current.images[current.currentImageIndex];
        const target = currentImage.annotations.find((item) => item.id === id);

        if (!target?.area || target.type !== 'box') {
          return current;
        }

        const minWidth = 24;
        const localSplitX = Math.max(
          target.area.x + minWidth,
          Math.min(splitX, target.area.x + target.area.width - minWidth)
        );
        const leftWidth = Math.round(localSplitX - target.area.x);
        const rightWidth = Math.round(target.area.width - leftWidth);

        if (leftWidth < minWidth || rightWidth < minWidth) {
          return current;
        }

        const leftObject: AnnotationObject = {
          ...target,
          id: createLocalAnnotationId(),
          area: {
            ...target.area,
            width: leftWidth
          }
        };

        const rightObject: AnnotationObject = {
          ...target,
          id: createLocalAnnotationId(),
          area: {
            ...target.area,
            x: Math.round(localSplitX),
            width: rightWidth
          }
        };
        splitObjects = [leftObject, rightObject];

        return {
          ...current,
          images: current.images.map((image, index) =>
            index === current.currentImageIndex
              ? {
                  ...image,
                  annotations: image.annotations.flatMap((item) =>
                    item.id === id ? [leftObject, rightObject] : [item]
                  )
                }
              : image
          ),
          selectedObjectId: leftObject.id
        };
      },
      { status: `Объект ${id} разделён` }
    );

    if (selectedProjectId && imageForRequest && isUuid(imageForRequest.id) && isUuid(id) && splitObjects.length === 2) {
      const remoteImageId = imageForRequest.id;
      api
        .deleteAnnotation(selectedProjectId, remoteImageId, id)
        .then(() =>
          Promise.all(splitObjects.map((object) => api.createAnnotation(selectedProjectId, remoteImageId, serializeAnnotationObject(object))))
        )
        .then((created) => {
          created.forEach((remote, index) => replaceAnnotationId(remoteImageId, splitObjects[index].id, remote));
          setStatusMessage(`Объект ${id} разделён и сохранён в БД`);
        })
        .catch((err) => setStatusMessage(err instanceof Error ? `Не удалось сохранить разделение: ${err.message}` : 'Не удалось сохранить разделение'));
    }
  };

  const handleDeleteSelected = () => {
    if (!workspace.selectedObjectId) {
      setStatusMessage('Сначала выберите объект');
      return;
    }

    deleteObject(workspace.selectedObjectId);
  };

  const handleResetCurrentAnnotations = () => {
    const imageForRequest = currentImage;
    const annotationIds = imageForRequest?.annotations.map((item) => item.id).filter(isUuid) ?? [];

    updateWorkspace(
      (current) => ({
        ...current,
        images: current.images.map((image, index) =>
          index === current.currentImageIndex ? { ...image, annotations: [] } : image
        ),
        selectedObjectId: null
      }),
      { status: 'Аннотации текущего изображения очищены' }
    );
    setIsMenuOpen(false);

    if (selectedProjectId && imageForRequest && isUuid(imageForRequest.id) && annotationIds.length) {
      const remoteImageId = imageForRequest.id;
      Promise.all(annotationIds.map((id) => api.deleteAnnotation(selectedProjectId, remoteImageId, id)))
        .then(() => setStatusMessage('Аннотации текущего изображения удалены из БД'))
        .catch((err) => setStatusMessage(err instanceof Error ? `Не удалось очистить БД: ${err.message}` : 'Не удалось очистить БД'));
    }
  };

  const toggleClassVisibility = (name: string) => {
    updateWorkspace(
      (current) => ({
        ...current,
        classList: current.classList.map((item) =>
          item.name === name ? { ...item, visible: !item.visible } : item
        )
      }),
      { recordHistory: false, status: `Видимость класса ${name} переключена` }
    );
  };

  const removeClassFromWorkspace = (name: string, status: string) => {
    updateWorkspace(
      (current) => {
        const nextClassList = current.classList.filter((item) => item.name !== name);
        const nextActiveLabel = current.activeLabel === name ? nextClassList[0]?.name ?? '' : current.activeLabel;

        return {
          ...current,
          classList: nextClassList,
          activeLabel: nextActiveLabel,
          selectedObjectId: current.images[current.currentImageIndex]?.annotations.some(
            (annotation) => annotation.id === current.selectedObjectId && annotation.label === name
          )
            ? null
            : current.selectedObjectId,
          images: current.images.map((image) => ({
            ...image,
            annotations: image.annotations.filter((annotation) => annotation.label !== name)
          }))
        };
      },
      { status }
    );
    setAnalysisClassNames((current) => current.filter((item) => item !== name));
  };

  const deleteClass = async (name: string) => {
    const remoteClass = availableClasses.find((item) => item.name_eng === name || item.name_ru === name);

    if (selectedProjectId && remoteClass) {
      setStatusMessage(`Удаляем класс ${name} на сервере...`);

      try {
        await api.deleteProjectClass(selectedProjectId, remoteClass.id);
        setAvailableClasses((current) => current.filter((item) => item.id !== remoteClass.id));
        removeClassFromWorkspace(name, `Класс ${name} удалён`);
      } catch (err) {
        setStatusMessage(err instanceof Error ? `Не удалось удалить класс: ${err.message}` : 'Не удалось удалить класс');
      }

      return;
    }

    removeClassFromWorkspace(name, `Класс ${name} удалён локально`);
  };

  const updateClassOpacity = (name: string, opacity: number) => {
    updateWorkspace(
      (current) => ({
        ...current,
        maskOpacity: opacity,
        classList: current.classList.map((item) => (item.name === name ? { ...item, opacity } : item))
      }),
      { recordHistory: false, status: `Прозрачность класса ${name}: ${Math.round(opacity * 100)}%` }
    );
  };

  const updateObjectOpacity = (id: AnnotationObject['id'], opacity: number) => {
    updateWorkspace(
      (current) => ({
        ...current,
        images: current.images.map((image, index) =>
          index === current.currentImageIndex
            ? {
                ...image,
                annotations: image.annotations.map((item) => (item.id === id ? { ...item, opacity } : item))
              }
            : image
        )
      }),
      { recordHistory: false, status: `Прозрачность объекта ${id}: ${Math.round(opacity * 100)}%` }
    );
  };

  const addClass = async () => {
    const value = newClassName.trim();

    if (!value) {
      setStatusMessage('Введите название класса');
      return;
    }

    if (workspace.classList.some((item) => item.name.toLowerCase() === value.toLowerCase())) {
      setStatusMessage('Такой класс уже существует');
      return;
    }

    if (selectedProjectId) {
      setStatusMessage(`Сохраняем класс ${value} на сервере...`);

      try {
        const createdClass = await api.createProjectClass(selectedProjectId, value);
        const classItem = classItemFromApi(createdClass);

        setAvailableClasses((current) =>
          current.some((item) => item.id === createdClass.id) ? current : [...current, createdClass]
        );
        updateWorkspace(
          (current) => ({
            ...current,
            classList: current.classList.some((item) => item.name.toLowerCase() === classItem.name.toLowerCase())
              ? current.classList
              : [...current.classList, classItem],
            activeLabel: classItem.name
          }),
          { status: `Класс ${classItem.name} добавлен на сервер` }
        );
        setAnalysisClassNames((current) => (current.includes(classItem.name) ? current : [...current, classItem.name]));
        setNewClassName('');
      } catch (err) {
        setStatusMessage(err instanceof Error ? `Не удалось добавить класс на сервер: ${err.message}` : 'Не удалось добавить класс на сервер');
      }

      return;
    }

    updateWorkspace(
      (current) => ({
        ...current,
        classList: [...current.classList, { name: value, source: 'manual', color: '#52b5ff', visible: true }],
        activeLabel: value
      }),
      { status: `Класс ${value} добавлен` }
    );
    setNewClassName('');
  };

  const toggleModel = (model: string, kind: 'segmentation' | 'detection') => {
    updateWorkspace(
      (current) => {
        const key = kind === 'segmentation' ? 'selectedSegmentationModels' : 'selectedDetectionModels';
        const isSelected = current[key].includes(model);

        return {
          ...current,
          selectedSegmentationModels: kind === 'segmentation' && !isSelected ? [model] : [],
          selectedDetectionModels: kind === 'detection' && !isSelected ? [model] : []
        };
      },
      { recordHistory: false, status: `Модель ${kind === 'segmentation' ? 'сегментации' : 'детекции'} обновлена` }
    );
  };

  const toggleAnalysisClass = (name: string) => {
    setAnalysisClassNames((current) =>
      current.includes(name) ? current.filter((item) => item !== name) : [...current, name]
    );
  };

  const handleRunModels = async () => {
    const selectedClassNames = analysisClassNames.length ? analysisClassNames : [];
    const activeModelNames = availableModels
      .filter((model) => selectedModelIds.includes(model.id))
      .map((model) => model.name);
    const selectedModelId = selectedModelIds[0];
    let classTypeIds = availableClasses
      .filter((classType) => {
        const className = classType.name_eng || classType.name_ru;
        return selectedClassNames.includes(className);
      })
      .map((classType) => classType.id);

    if (!selectedModelIds.length) {
      setStatusMessage('Выберите модель для анализа');
      return;
    }

    if (selectedModelIds.length > 1) {
      setStatusMessage('Выберите только одну модель для анализа');
      return;
    }

    if (!selectedClassNames.length) {
      setStatusMessage('Выберите хотя бы один класс для анализа');
      return;
    }

    if (!selectedProjectId || !currentImage || !isUuid(currentImage.id)) {
      setStatusMessage('Выберите изображение проекта из backend');
      return;
    }

    const currentImageId = currentImage.id;

    setIsRunningModels(true);
    setStatusMessage(`Подключаем WebSocket анализа: ${activeModelNames.join(', ')}; классы: ${selectedClassNames.join(', ')}`);

    const handleAnalysisMessage = (message: AnalysisSocketMessage) => {
      if (message.type === 'subscribed') {
        setStatusMessage('WebSocket подключён, запускаем анализ...');
      }
      if (message.type === 'task_created') {
        setStatusMessage(`Задача анализа создана: ${(message as { task_id: string }).task_id}`);
      }
      if (message.type === 'task_update') {
        const event = (message as { event?: string }).event;
        setStatusMessage(event === 'completed' ? 'Модель вернула результат, обновляем аннотации...' : `Статус анализа: ${event}`);
      }
    };

    try {
      if (classTypeIds.length !== selectedClassNames.length) {
        setStatusMessage('Синхронизируем классы проекта перед анализом...');
        await Promise.all(selectedClassNames.map((name) => ensureRemoteClass(selectedProjectId, name)));
        const refreshedClasses = await api.getProjectClasses(selectedProjectId);
        setAvailableClasses(refreshedClasses);
        classTypeIds = refreshedClasses
          .filter((classType) => selectedClassNames.includes(classType.name_eng || classType.name_ru))
          .map((classType) => classType.id);
      }

      await api.startAnalysisViaWebSocket({
        imageId: currentImageId,
        modelConfigId: selectedModelId,
        classTypeIds,
        onMessage: handleAnalysisMessage
      });

      const annotations = await api.getAnnotations(selectedProjectId, currentImageId);
      const generated = annotations.map(annotationFromApi);

      updateWorkspace(
        (current) => ({
          ...current,
          images: current.images.map((image, index) =>
            index === current.currentImageIndex
              ? { ...image, annotations: mergeAnnotationObjects(generated, image.annotations) }
              : image
          ),
          selectedObjectId: generated[0]?.id ?? current.selectedObjectId
        }),
        { status: `WebSocket анализ завершён, аннотаций: ${generated.length}` }
      );
    } catch (err) {
      setStatusMessage(err instanceof Error ? `WebSocket не прошёл, пробуем REST: ${err.message}` : 'WebSocket не прошёл, пробуем REST');

      try {
        const annotations = await api.runModels(selectedProjectId, currentImageId, [selectedModelId], selectedClassNames[0]);
        const generated = annotations.map(annotationFromApi);

        updateWorkspace(
          (current) => ({
            ...current,
            images: current.images.map((image, index) =>
              index === current.currentImageIndex
                ? { ...image, annotations: mergeAnnotationObjects(generated, image.annotations) }
                : image
            ),
            selectedObjectId: generated[0]?.id ?? current.selectedObjectId
          }),
          { status: `REST fallback вернул авторазметку: ${generated.length}` }
        );
      } catch (fallbackErr) {
        setStatusMessage(
          fallbackErr instanceof Error ? `Не удалось запустить модели: ${fallbackErr.message}` : 'Не удалось запустить модели'
        );
      }
    } finally {
      setIsRunningModels(false);
    }
  };

  return (
    <PageTransition>
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*,application/json,.json"
        multiple
        onChange={handleImageUpload}
        className="hidden"
      />

      <div className="mx-auto max-w-[1720px] px-4 pb-6 pt-4">
        <div className="min-w-0">
          <section className="min-h-0 min-w-0">
            <WorkspaceCanvas
              activeTool={workspace.activeTool}
              onToolChange={(tool) =>
                updateWorkspace((current) => ({ ...current, activeTool: tool }), {
                  recordHistory: false,
                  status: tool ? `Активный инструмент: ${tool}` : 'Инструмент выключен'
                })
              }
              activeLabel={workspace.activeLabel}
              maskOpacity={workspace.maskOpacity}
              onMaskOpacityChange={(opacity) =>
                updateWorkspace(
                  (current) => ({
                    ...current,
                    maskOpacity: opacity
                  }),
                  {
                    recordHistory: false,
                    status: `Прозрачность маски: ${Math.round(opacity * 100)}%`
                  }
                )
              }
              opacityTargetMode={opacityTargetMode}
              opacityClassName={opacityClassName}
              onOpacityTargetModeChange={setOpacityTargetMode}
              onOpacityClassNameChange={setOpacityClassName}
              onClassOpacityChange={updateClassOpacity}
              onObjectOpacityChange={updateObjectOpacity}
              compareViewMode="single"
              compareLeftSource="Imported"
              compareRightSource="Manual"
              classList={workspace.classList}
              newClassName={newClassName}
              imageName={isLoadingRemoteImages ? 'Загрузка...' : currentImage.name}
              imageSrc={currentImage.src}
              imageIndex={workspace.currentImageIndex}
              imageCount={workspace.images.length}
              canUndo={historyIndex > 0}
              canRedo={historyIndex < history.length - 1}
              statusMessage={statusMessage}
              isMenuOpen={isMenuOpen}
              hasSavedDraft={hasSavedDraft}
              selectedObjectId={workspace.selectedObjectId}
              objects={objects}
              hiddenLabels={hiddenLabels}
              segmentationModels={segmentationModels}
              detectionModels={detectionModels}
              selectedSegmentationModels={workspace.selectedSegmentationModels}
              selectedDetectionModels={workspace.selectedDetectionModels}
              analysisClassNames={analysisClassNames}
              isRunningModels={isRunningModels}
              onToggleMenu={() => setIsMenuOpen((current) => !current)}
              onCloseMenu={() => setIsMenuOpen(false)}
              onSave={handleSave}
              onUndo={handleUndo}
              onRedo={handleRedo}
              onFirstImage={() => setCurrentImageIndex(0)}
              onPreviousImage={() => setCurrentImageIndex(workspace.currentImageIndex - 1)}
              onNextImage={() => setCurrentImageIndex(workspace.currentImageIndex + 1)}
              onLastImage={() => setCurrentImageIndex(workspace.images.length - 1)}
              onSelectImageByIndex={(index) => setCurrentImageIndex(index)}
              onOpenImagePicker={() => fileInputRef.current?.click()}
              onLoadSaved={handleLoadSaved}
              onExportProject={handleExportProject}
              onResetAnnotations={handleResetCurrentAnnotations}
              onSelectObject={(id) =>
                updateWorkspace((current) => ({ ...current, selectedObjectId: id }), { recordHistory: false })
              }
              onDeleteObject={deleteObject}
              onSelectClass={(name) =>
                updateWorkspace((current) => ({ ...current, activeLabel: name }), {
                  recordHistory: false,
                  status: `Активный класс: ${name}`
                })
              }
              onToggleClassVisibility={toggleClassVisibility}
              onDeleteClass={deleteClass}
              onToggleAnalysisClass={toggleAnalysisClass}
              onToggleModel={toggleModel}
              onRunModels={handleRunModels}
              onNewClassNameChange={setNewClassName}
              onAddClass={addClass}
              onCreateObject={createObject}
              onUpdateObject={updateObject}
              onSplitObject={splitObject}
            />
          </section>
        </div>
      </div>
    </PageTransition>
  );
};

export default WorkspacePage;
