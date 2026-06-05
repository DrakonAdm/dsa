import { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, Lock, Trash2, Unlock, Wand2 } from 'lucide-react';
import { Circle, Group, Image as KonvaImage, Layer, Line, Rect, Stage, Text } from 'react-konva';

const FALLBACK_CANVAS_WIDTH = 1200;
const FALLBACK_CANVAS_HEIGHT = 720;
const CANVAS_PAN_DRAG_THRESHOLD = 4;
const MIN_CANVAS_ZOOM = 0.6;
const MAX_CANVAS_ZOOM = 8;
const CANVAS_ZOOM_STEP = 1.25;
const POLYGON_CORRECTION_MIN_SCREEN_DISTANCE = 4;
const POLYGON_CORRECTION_HIT_SCREEN_DISTANCE = 34;
const MIN_BOX_SIZE = 8;
const RESIZE_HANDLE_SIZE = 10;

export type ToolMode = 'select' | 'box' | 'polygon' | 'zoom' | 'move' | 'brush' | 'eraser' | 'split';
export type ActiveToolMode = ToolMode | null;

export interface Area {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface PolygonPoint {
  x: number;
  y: number;
}

interface PolygonCorrectionDraft {
  target: 'draft' | 'object';
  objectId?: AnnotationObject['id'];
  startIndex: number;
  points: PolygonPoint[];
  hasMoved: boolean;
}

interface PolygonDraftHit {
  index: number;
  distance: number;
}

type BoxResizeHandle = 'nw' | 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w';

interface ObjectEditPreview {
  id: AnnotationObject['id'];
  patch: Partial<AnnotationObject>;
}

export interface AnnotationObject {
  id: number | string;
  label: string;
  color: string;
  type: 'box' | 'polygon' | 'brush';
  operation?: 'paint' | 'erase';
  source: 'manual' | 'imported' | 'model';
  modelName?: string;
  score?: number;
  opacity?: number;
  locked?: boolean;
  area?: Area;
  points?: PolygonPoint[];
}

export type CompareViewMode = 'single' | 'split';
export type OpacityTargetMode = 'class' | 'object';

export interface WorkspaceClassItem {
  name: string;
  source: 'imported' | 'manual' | 'model';
  color: string;
  visible: boolean;
  opacity?: number;
}

export interface WorkspaceModelItem {
  id: number;
  name: string;
  type: string;
}

interface WorkspaceCanvasProps {
  activeTool: ActiveToolMode;
  onToolChange: (tool: ActiveToolMode) => void;
  activeLabel: string;
  maskOpacity: number;
  onMaskOpacityChange: (opacity: number) => void;
  opacityTargetMode: OpacityTargetMode;
  opacityClassName: string;
  onOpacityTargetModeChange: (mode: OpacityTargetMode) => void;
  onOpacityClassNameChange: (name: string) => void;
  onClassOpacityChange: (name: string, opacity: number) => void;
  onObjectOpacityChange: (id: AnnotationObject['id'], opacity: number) => void;
  compareViewMode: CompareViewMode;
  compareLeftSource: string;
  compareRightSource: string;
  classList: WorkspaceClassItem[];
  newClassName: string;
  imageName: string;
  imageSrc: string;
  imageIndex: number;
  imageCount: number;
  canUndo: boolean;
  canRedo: boolean;
  statusMessage: string;
  isMenuOpen: boolean;
  hasSavedDraft: boolean;
  selectedObjectId: AnnotationObject['id'] | null;
  objects: AnnotationObject[];
  hiddenLabels: string[];
  segmentationModels: WorkspaceModelItem[];
  detectionModels: WorkspaceModelItem[];
  selectedSegmentationModels: string[];
  selectedDetectionModels: string[];
  analysisClassNames: string[];
  isRunningModels: boolean;
  onToggleMenu: () => void;
  onCloseMenu: () => void;
  onSave: () => void;
  onUndo: () => void;
  onRedo: () => void;
  onFirstImage: () => void;
  onPreviousImage: () => void;
  onNextImage: () => void;
  onLastImage: () => void;
  onSelectImageByIndex: (index: number) => void;
  onOpenImagePicker: () => void;
  onLoadSaved: () => void;
  onExportProject: () => void;
  onResetAnnotations: () => void;
  onSelectObject: (id: AnnotationObject['id'] | null) => void;
  onDeleteObject: (id: AnnotationObject['id']) => void;
  onSelectClass: (name: string) => void;
  onToggleClassVisibility: (name: string) => void;
  onDeleteClass: (name: string) => void;
  onToggleAnalysisClass: (name: string) => void;
  onToggleModel: (model: string, kind: 'segmentation' | 'detection') => void;
  onRunModels: () => void;
  onNewClassNameChange: (name: string) => void;
  onAddClass: () => void;
  onCreateObject: (object: Omit<AnnotationObject, 'id'>) => void;
  onUpdateObject: (id: AnnotationObject['id'], patch: Partial<AnnotationObject>) => void;
  onSplitObject: (id: AnnotationObject['id'], splitX: number) => void;
}

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

const getPolygonBounds = (points: PolygonPoint[]): Area => {
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);

  return {
    x: Math.min(...xs),
    y: Math.min(...ys),
    width: Math.max(...xs) - Math.min(...xs),
    height: Math.max(...ys) - Math.min(...ys)
  };
};

const clampAreaToImage = (area: Area, imageSize: Pick<Area, 'width' | 'height'>): Area => {
  const width = clamp(area.width, MIN_BOX_SIZE, imageSize.width);
  const height = clamp(area.height, MIN_BOX_SIZE, imageSize.height);
  const x = clamp(area.x, 0, imageSize.width - width);
  const y = clamp(area.y, 0, imageSize.height - height);

  return { x, y, width, height };
};

const getBoxResizeHandles = (area: Area): Array<{ id: BoxResizeHandle; x: number; y: number }> => [
  { id: 'nw', x: area.x, y: area.y },
  { id: 'n', x: area.x + area.width / 2, y: area.y },
  { id: 'ne', x: area.x + area.width, y: area.y },
  { id: 'e', x: area.x + area.width, y: area.y + area.height / 2 },
  { id: 'se', x: area.x + area.width, y: area.y + area.height },
  { id: 's', x: area.x + area.width / 2, y: area.y + area.height },
  { id: 'sw', x: area.x, y: area.y + area.height },
  { id: 'w', x: area.x, y: area.y + area.height / 2 }
];

const resizeBoxArea = (area: Area, handle: BoxResizeHandle, point: PolygonPoint, imageSize: Pick<Area, 'width' | 'height'>): Area => {
  let left = area.x;
  let right = area.x + area.width;
  let top = area.y;
  let bottom = area.y + area.height;

  if (handle.includes('w')) {
    left = clamp(point.x, 0, right - MIN_BOX_SIZE);
  }

  if (handle.includes('e')) {
    right = clamp(point.x, left + MIN_BOX_SIZE, imageSize.width);
  }

  if (handle.includes('n')) {
    top = clamp(point.y, 0, bottom - MIN_BOX_SIZE);
  }

  if (handle.includes('s')) {
    bottom = clamp(point.y, top + MIN_BOX_SIZE, imageSize.height);
  }

  if (handle === 'n' || handle === 's') {
    left = area.x;
    right = area.x + area.width;
  }

  if (handle === 'e' || handle === 'w') {
    top = area.y;
    bottom = area.y + area.height;
  }

  return {
    x: Math.round(left),
    y: Math.round(top),
    width: Math.round(right - left),
    height: Math.round(bottom - top)
  };
};

const dedupeConsecutivePoints = (points: PolygonPoint[]) =>
  points.filter((point, index) => {
    const previous = points[index - 1];
    return !previous || Math.hypot(point.x - previous.x, point.y - previous.y) >= 0.5;
  });

const replacePolygonSegment = (
  points: PolygonPoint[],
  startIndex: number,
  endIndex: number,
  correctionPoints: PolygonPoint[]
) => {
  if (
    startIndex < 0 ||
    endIndex < 0 ||
    startIndex >= points.length ||
    endIndex >= points.length ||
    startIndex === endIndex
  ) {
    return points;
  }

  const path = dedupeConsecutivePoints([
    points[startIndex],
    ...correctionPoints.slice(1),
    points[endIndex]
  ]);

  if (startIndex < endIndex) {
    return [
      ...points.slice(0, startIndex),
      ...path,
      ...points.slice(endIndex + 1)
    ];
  }

  return [
    ...path,
    ...points.slice(endIndex + 1, startIndex)
  ];
};

const getObjectSourceKey = (object: AnnotationObject) => {
  if (object.source === 'model') {
    return object.modelName ?? 'Model';
  }

  if (object.source === 'imported') {
    return 'Imported';
  }

  return 'Manual';
};

const getClassCountLabel = (count: number) => {
  const mod10 = count % 10;
  const mod100 = count % 100;

  if (mod10 === 1 && mod100 !== 11) {
    return `${count} класс`;
  }

  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) {
    return `${count} класса`;
  }

  return `${count} классов`;
};

const modelTypeLabel: Record<string, string> = {
  segmentation: 'Сегментация',
  sahi_segmentation: 'SAHI сегментация',
  detection: 'Детекция',
  sahi_detection: 'SAHI детекция'
};

const WorkspaceCanvas: React.FC<WorkspaceCanvasProps> = ({
  activeTool,
  onToolChange,
  activeLabel,
  maskOpacity,
  onMaskOpacityChange,
  opacityTargetMode,
  opacityClassName,
  onOpacityTargetModeChange,
  onOpacityClassNameChange,
  onClassOpacityChange,
  onObjectOpacityChange,
  compareViewMode,
  compareLeftSource,
  compareRightSource,
  classList,
  newClassName,
  imageName,
  imageSrc,
  imageIndex,
  imageCount,
  canUndo,
  canRedo,
  statusMessage,
  isMenuOpen,
  hasSavedDraft,
  selectedObjectId,
  objects,
  hiddenLabels,
  segmentationModels,
  detectionModels,
  selectedSegmentationModels,
  selectedDetectionModels,
  analysisClassNames,
  isRunningModels,
  onToggleMenu,
  onCloseMenu,
  onSave,
  onUndo,
  onRedo,
  onFirstImage,
  onPreviousImage,
  onNextImage,
  onLastImage,
  onSelectImageByIndex,
  onOpenImagePicker,
  onLoadSaved,
  onExportProject,
  onResetAnnotations,
  onSelectObject,
  onDeleteObject,
  onSelectClass,
  onToggleClassVisibility,
  onDeleteClass,
  onToggleAnalysisClass,
  onToggleModel,
  onRunModels,
  onNewClassNameChange,
  onAddClass,
  onCreateObject,
  onUpdateObject,
  onSplitObject
}) => {
  const [image, setImage] = useState<HTMLImageElement | null>(null);
  const [imageSize, setImageSize] = useState({
    width: FALLBACK_CANVAS_WIDTH,
    height: FALLBACK_CANVAS_HEIGHT
  });
  const [stageBounds, setStageBounds] = useState({
    width: FALLBACK_CANVAS_WIDTH,
    height: FALLBACK_CANVAS_HEIGHT
  });
  const [draftBox, setDraftBox] = useState<Area | null>(null);
  const [polygonDraft, setPolygonDraft] = useState<PolygonPoint[]>([]);
  const [brushDraft, setBrushDraft] = useState<PolygonPoint[]>([]);
  const [polygonCorrectionDraft, setPolygonCorrectionDraft] = useState<PolygonCorrectionDraft | null>(null);
  const [drawingStart, setDrawingStart] = useState<PolygonPoint | null>(null);
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [isShiftPressed, setIsShiftPressed] = useState(false);
  const [isCtrlPressed, setIsCtrlPressed] = useState(false);
  const [indexInput, setIndexInput] = useState(String(imageIndex + 1));
  const [objectEditPreview, setObjectEditPreview] = useState<ObjectEditPreview | null>(null);
  const polygonCorrectionDraftRef = useRef<PolygonCorrectionDraft | null>(null);
  const leftButtonDownRef = useRef(false);
  const panStartRef = useRef<{ x: number; y: number } | null>(null);
  const panStartScreenRef = useRef<PolygonPoint | null>(null);
  const hasDraggedCanvasRef = useRef(false);
  const isPanningRef = useRef(false);
  const pendingPolygonClickRef = useRef<PolygonPoint | null>(null);
  const objectMoveIntentRef = useRef<AnnotationObject['id'] | null>(null);
  const objectMoveDragRef = useRef<AnnotationObject['id'] | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!imageSrc) {
      setImage(null);
      setImageSize({
        width: FALLBACK_CANVAS_WIDTH,
        height: FALLBACK_CANVAS_HEIGHT
      });
      return undefined;
    }

    const nextImage = new window.Image();
    nextImage.src = imageSrc;
    nextImage.onload = () => {
      setImage(nextImage);
      setImageSize({
        width: nextImage.naturalWidth || FALLBACK_CANVAS_WIDTH,
        height: nextImage.naturalHeight || FALLBACK_CANVAS_HEIGHT
      });
    };
    nextImage.onerror = () => {
      setImage(null);
      setImageSize({
        width: FALLBACK_CANVAS_WIDTH,
        height: FALLBACK_CANVAS_HEIGHT
      });
    };

    return () => {
      setImage(null);
    };
  }, [imageSrc]);

  useEffect(() => {
    setZoom(1);
    setOffset({ x: 0, y: 0 });
    setPolygonDraft([]);
    setPolygonCorrectionDraft(null);
    setBrushDraft([]);
    setDraftBox(null);
    setDrawingStart(null);
    setObjectEditPreview(null);
    polygonCorrectionDraftRef.current = null;
    leftButtonDownRef.current = false;
    panStartRef.current = null;
    panStartScreenRef.current = null;
    hasDraggedCanvasRef.current = false;
    isPanningRef.current = false;
    pendingPolygonClickRef.current = null;
    objectMoveIntentRef.current = null;
    objectMoveDragRef.current = null;
  }, [imageSrc]);

  useEffect(() => {
    const element = containerRef.current;

    if (!element) {
      return undefined;
    }

    const updateStageSize = () => {
      setStageBounds({
        width: element.clientWidth,
        height: element.clientHeight
      });
    };

    updateStageSize();

    const resizeObserver = new ResizeObserver(updateStageSize);
    resizeObserver.observe(element);

    return () => resizeObserver.disconnect();
  }, []);

  useEffect(() => {
    setIndexInput(String(imageIndex + 1));
  }, [imageIndex]);

  useEffect(() => {
    setObjectEditPreview(null);
  }, [selectedObjectId, activeTool]);

  useEffect(() => {
    if (activeTool && activeTool !== 'box' && activeTool !== 'polygon') {
      onToolChange(null);
    }
  }, [activeTool, onToolChange]);

  useEffect(() => {
    if (!isMenuOpen) {
      return undefined;
    }

    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node;

      if (menuRef.current?.contains(target) || menuButtonRef.current?.contains(target)) {
        return;
      }

      onCloseMenu();
    };

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onCloseMenu();
      }
    };

    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('keydown', handleEscape);

    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [isMenuOpen, onCloseMenu]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Shift' || event.code === 'ShiftLeft' || event.code === 'ShiftRight' || event.shiftKey) {
        setIsShiftPressed(true);
      }

      if (event.key === 'Control' || event.key === 'Meta') {
        setIsCtrlPressed(true);
      }

      if (event.key === 'Escape') {
        updatePolygonCorrectionDraft(null);
      }
    };

    const handleKeyUp = (event: KeyboardEvent) => {
      if (event.key === 'Shift' || event.code === 'ShiftLeft' || event.code === 'ShiftRight' || !event.shiftKey) {
        setIsShiftPressed(false);
      }

      if (event.key === 'Control' || event.key === 'Meta') {
        setIsCtrlPressed(false);
      }
    };

    const handleWindowBlur = () => {
      setIsShiftPressed(false);
      setIsCtrlPressed(false);
    };

    const handleWindowMouseUp = () => {
      leftButtonDownRef.current = false;
      pendingPolygonClickRef.current = null;
      stopCanvasPan();
    };

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);
    window.addEventListener('blur', handleWindowBlur);
    window.addEventListener('mouseup', handleWindowMouseUp);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
      window.removeEventListener('blur', handleWindowBlur);
      window.removeEventListener('mouseup', handleWindowMouseUp);
    };
  }, []);

  const imageAspectRatio = imageSize.height / imageSize.width;
  const availableStageWidth = Math.max(320, stageBounds.width);
  const availableStageHeight = Math.max(240, stageBounds.height);
  const stageWidth = Math.round(Math.min(availableStageWidth, availableStageHeight / imageAspectRatio));
  const stageHeight = Math.round(stageWidth * imageAspectRatio);
  const baseScale = stageWidth / imageSize.width;
  const canvasScale = baseScale * zoom;
  const hasActiveClass = Boolean(activeLabel.trim());
  const visibleObjects = useMemo(
    () => objects.filter((item) => !hiddenLabels.includes(item.label)),
    [objects, hiddenLabels]
  );
  const previewVisibleObjects = useMemo(
    () =>
      visibleObjects.map((item) =>
        objectEditPreview?.id === item.id ? { ...item, ...objectEditPreview.patch } : item
      ),
    [objectEditPreview, visibleObjects]
  );
  const selectedObject = useMemo(
    () => previewVisibleObjects.find((item) => item.id === selectedObjectId) ?? null,
    [selectedObjectId, previewVisibleObjects]
  );
  const selectedPolygonObject = useMemo(
    () =>
      selectedObject?.type === 'polygon' && (selectedObject.points?.length ?? 0) >= 3 ? selectedObject : null,
    [selectedObject]
  );
  const isPolygonCorrectionMode = activeTool === 'polygon' && (isShiftPressed || Boolean(polygonCorrectionDraft));
  const listedObjects = useMemo(
    () => previewVisibleObjects.filter((item) => !(item.type === 'brush' && item.operation === 'erase')),
    [previewVisibleObjects]
  );
  const getObjectsForSource = (sourceKey: string) =>
    previewVisibleObjects.filter((item) => getObjectSourceKey(item) === sourceKey);
  const selectedOpacityClass = classList.find((item) => item.name === opacityClassName) ?? classList[0] ?? null;
  const currentOpacity =
    opacityTargetMode === 'object' && selectedObject
      ? selectedObject.opacity ?? classList.find((item) => item.name === selectedObject.label)?.opacity ?? maskOpacity
      : selectedOpacityClass?.opacity ?? maskOpacity;
  const getObjectOpacity = (object: AnnotationObject) =>
    object.opacity ?? classList.find((item) => item.name === object.label)?.opacity ?? maskOpacity;
  const standardSegmentationModels = useMemo(
    () => segmentationModels.filter((model) => model.type === 'segmentation'),
    [segmentationModels]
  );
  const sahiSegmentationModels = useMemo(
    () => segmentationModels.filter((model) => model.type === 'sahi_segmentation'),
    [segmentationModels]
  );
  const standardDetectionModels = useMemo(
    () => detectionModels.filter((model) => model.type === 'detection'),
    [detectionModels]
  );
  const sahiDetectionModels = useMemo(
    () => detectionModels.filter((model) => model.type === 'sahi_detection'),
    [detectionModels]
  );
  const renderModelOptions = (
    models: WorkspaceModelItem[],
    selectedModels: string[],
    kind: 'segmentation' | 'detection',
    checkboxClassName: string,
    badgeClassName: string,
    emptyMessage: string
  ) => (
    <div className="mt-2 grid gap-1.5">
      {models.map((model) => {
        const modelKey = String(model.id);
        const isChecked = selectedModels.includes(modelKey);

        return (
          <label
            key={model.id}
            className="flex cursor-pointer items-center gap-2 rounded-lg border border-slate-800 bg-slate-900/70 px-2.5 py-2 text-xs text-slate-200"
          >
            <input
              type="checkbox"
              checked={isChecked}
              onChange={() => onToggleModel(modelKey, kind)}
              className={checkboxClassName}
            />
            <span className="min-w-0 truncate">{model.name}</span>
            <span className={badgeClassName}>
              {modelTypeLabel[model.type] ?? model.type}
            </span>
          </label>
        );
      })}
      {!models.length && <div className="rounded-lg bg-slate-900/70 px-2.5 py-2 text-xs text-slate-500">{emptyMessage}</div>}
    </div>
  );

  const comparisonLeftObjects = useMemo(
    () => (compareViewMode === 'split' ? getObjectsForSource(compareLeftSource) : previewVisibleObjects),
    [compareViewMode, compareLeftSource, previewVisibleObjects]
  );
  const comparisonRightObjects = useMemo(
    () => getObjectsForSource(compareRightSource),
    [compareRightSource, previewVisibleObjects]
  );

  const getPointer = (event: any): PolygonPoint | null => {
    const stage = event.target.getStage();
    const pointer = stage?.getPointerPosition();

    if (!pointer) {
      return null;
    }

    return {
      x: Math.round(clamp((pointer.x - offset.x) / canvasScale, 0, imageSize.width)),
      y: Math.round(clamp((pointer.y - offset.y) / canvasScale, 0, imageSize.height))
    };
  };

  const zoomAtPointer = (screenX: number, screenY: number, direction: 1 | -1) => {
    const nextZoom = clamp(direction > 0 ? zoom * CANVAS_ZOOM_STEP : zoom / CANVAS_ZOOM_STEP, MIN_CANVAS_ZOOM, MAX_CANVAS_ZOOM);
    const worldX = (screenX - offset.x) / canvasScale;
    const worldY = (screenY - offset.y) / canvasScale;

    setZoom(nextZoom);
    setOffset({
      x: screenX - worldX * baseScale * nextZoom,
      y: screenY - worldY * baseScale * nextZoom
    });
  };

  const getStagePointer = (event: any): PolygonPoint | null => {
    const stage = event.target.getStage();
    return stage?.getPointerPosition() ?? null;
  };

  const setCanvasPanning = (nextIsPanning: boolean) => {
    isPanningRef.current = nextIsPanning;
  };

  const setCanvasPanStart = (nextPanStart: { x: number; y: number } | null) => {
    panStartRef.current = nextPanStart;
  };

  const startCanvasPan = (event: any, immediate = true) => {
    const pointer = getStagePointer(event);

    if (!pointer) {
      return;
    }

    setCanvasPanStart({ x: pointer.x - offset.x, y: pointer.y - offset.y });
    panStartScreenRef.current = pointer;
    hasDraggedCanvasRef.current = false;
    setCanvasPanning(immediate);
  };

  const updateCanvasPan = (event: any) => {
    const pointer = getStagePointer(event);
    const currentPanStart = panStartRef.current;

    if (!pointer || !currentPanStart) {
      return false;
    }

    const startScreenPoint = panStartScreenRef.current;

    if (!isPanningRef.current && startScreenPoint) {
      const distance = Math.hypot(pointer.x - startScreenPoint.x, pointer.y - startScreenPoint.y);

      if (distance < CANVAS_PAN_DRAG_THRESHOLD) {
        return false;
      }

      setCanvasPanning(true);
    }

    hasDraggedCanvasRef.current = true;
    setOffset({ x: pointer.x - currentPanStart.x, y: pointer.y - currentPanStart.y });
    return true;
  };

  const stopCanvasPan = () => {
    setCanvasPanning(false);
    setCanvasPanStart(null);
    panStartScreenRef.current = null;
  };

  const updateCurrentOpacity = (opacity: number) => {
    if (opacityTargetMode === 'object' && selectedObject) {
      if (selectedObject.locked) {
        return;
      }

      onObjectOpacityChange(selectedObject.id, opacity);
      return;
    }

    if (selectedOpacityClass) {
      onClassOpacityChange(selectedOpacityClass.name, opacity);
      return;
    }

    onMaskOpacityChange(opacity);
  };

  const updateObjectClass = (object: AnnotationObject, nextLabel: string) => {
    if (object.locked || object.label === nextLabel) {
      return;
    }

    const nextClass = classList.find((item) => item.name === nextLabel);

    onUpdateObject(object.id, {
      label: nextLabel,
      color: nextClass?.color ?? object.color
    });
  };

  const toggleObjectLock = (object: AnnotationObject) => {
    onUpdateObject(object.id, { locked: !object.locked });
  };

  const appendPolygonDraftPoint = (point: PolygonPoint, minDistance = 0) => {
    setPolygonDraft((current) => {
      const lastPoint = current[current.length - 1];

      if (lastPoint && Math.hypot(point.x - lastPoint.x, point.y - lastPoint.y) < minDistance) {
        return current;
      }

      return [...current, point];
    });
  };

  const updatePolygonCorrectionDraft = (nextDraft: PolygonCorrectionDraft | null) => {
    polygonCorrectionDraftRef.current = nextDraft;
    setPolygonCorrectionDraft(nextDraft);
  };

  const findNearestPolygonPoint = (
    points: PolygonPoint[],
    point: PolygonPoint,
    maxDistance: number
  ): PolygonDraftHit | null => {
    let closest: PolygonDraftHit | null = null;

    points.forEach((draftPoint, index) => {
      const distance = Math.hypot(point.x - draftPoint.x, point.y - draftPoint.y);

      if (distance <= maxDistance && (!closest || distance < closest.distance)) {
        closest = { index, distance };
      }
    });

    return closest;
  };

  const getPolygonCorrectionTarget = (draft = polygonCorrectionDraftRef.current) => {
    if (draft?.target === 'object') {
      const object = visibleObjects.find(
        (item) => item.id === draft.objectId && !item.locked && item.type === 'polygon' && (item.points?.length ?? 0) >= 3
      );

      if (!object?.points) {
        return null;
      }

      return {
        target: 'object' as const,
        objectId: object.id,
        points: object.points
      };
    }

    if (polygonDraft.length >= 3) {
      return {
        target: 'draft' as const,
        points: polygonDraft
      };
    }

    if (selectedPolygonObject?.points && !selectedPolygonObject.locked) {
      return {
        target: 'object' as const,
        objectId: selectedPolygonObject.id,
        points: selectedPolygonObject.points
      };
    }

    return null;
  };

  const appendPolygonCorrectionPoint = (point: PolygonPoint) => {
    const draft = polygonCorrectionDraftRef.current;

    if (!draft) {
      return;
    }

    const lastPoint = draft.points[draft.points.length - 1];
    const minDistance = POLYGON_CORRECTION_MIN_SCREEN_DISTANCE / canvasScale;

    if (lastPoint && Math.hypot(point.x - lastPoint.x, point.y - lastPoint.y) < minDistance) {
      return;
    }

    updatePolygonCorrectionDraft({
      ...draft,
      points: [...draft.points, point],
      hasMoved: true
    });
  };

  const applyPolygonCorrection = (
    correctionDraft: PolygonCorrectionDraft,
    endIndex: number,
    correctionPoints: PolygonPoint[]
  ) => {
    const target = getPolygonCorrectionTarget(correctionDraft);

    if (!target) {
      return;
    }

    const nextPoints = replacePolygonSegment(
      target.points,
      correctionDraft.startIndex,
      endIndex,
      correctionPoints
    );

    if (nextPoints.length < 3) {
      return;
    }

    if (target.target === 'draft') {
      setPolygonDraft(nextPoints);
      return;
    }

    onUpdateObject(target.objectId, {
      points: nextPoints,
      area: getPolygonBounds(nextPoints)
    });
  };

  const startBox = (event: any) => {
    if (!hasActiveClass) {
      return;
    }

    const pointer = getPointer(event);

    if (!pointer) {
      return;
    }

    setDrawingStart(pointer);
    setDraftBox({ x: pointer.x, y: pointer.y, width: 0, height: 0 });
    onSelectObject(null);
  };

  const updateBox = (event: any) => {
    const pointer = getPointer(event);

    if (!pointer || !drawingStart) {
      return;
    }

    const x = Math.min(pointer.x, drawingStart.x);
    const y = Math.min(pointer.y, drawingStart.y);
    const width = Math.abs(pointer.x - drawingStart.x);
    const height = Math.abs(pointer.y - drawingStart.y);

    setDraftBox({ x, y, width, height });
  };

  const finishBox = () => {
    if (hasActiveClass && activeTool === 'box' && draftBox && draftBox.width > 12 && draftBox.height > 12) {
      onCreateObject({
        type: 'box',
        label: activeLabel,
        color: '#7CFC8A',
        source: 'manual',
        area: {
          x: Math.round(draftBox.x),
          y: Math.round(draftBox.y),
          width: Math.round(draftBox.width),
          height: Math.round(draftBox.height)
        }
      });
    }

    setDraftBox(null);
    setDrawingStart(null);
  };

  const addPolygonPoint = (event: any) => {
    if (!hasActiveClass) {
      return;
    }

    const pointer = getPointer(event);

    if (!pointer) {
      return;
    }

    if (polygonDraft.length >= 3) {
      const firstPoint = polygonDraft[0];
      const distance = Math.hypot(pointer.x - firstPoint.x, pointer.y - firstPoint.y);

      if (distance < 18) {
        onCreateObject({
          type: 'polygon',
          label: activeLabel,
          color: '#7CFC8A',
          source: 'manual',
          points: polygonDraft,
          area: getPolygonBounds(polygonDraft)
        });
        setPolygonDraft([]);
        return;
      }
    }

    appendPolygonDraftPoint(pointer);
    onSelectObject(null);
  };

  const startPolygonCorrection = (event: any, objectOverride?: AnnotationObject) => {
    if (event.evt.button !== 0) {
      return;
    }

    const pointer = getPointer(event);

    if (!pointer) {
      return;
    }

    const target =
      objectOverride?.type === 'polygon' && !objectOverride.locked && objectOverride.points && objectOverride.points.length >= 3
        ? {
            target: 'object' as const,
            objectId: objectOverride.id,
            points: objectOverride.points
          }
        : getPolygonCorrectionTarget();

    if (!target) {
      return;
    }

    const nearest = findNearestPolygonPoint(target.points, pointer, POLYGON_CORRECTION_HIT_SCREEN_DISTANCE / canvasScale);

    if (!nearest) {
      return;
    }

    event.evt.preventDefault();
    updatePolygonCorrectionDraft({
      target: target.target,
      objectId: target.target === 'object' ? target.objectId : undefined,
      startIndex: nearest.index,
      points: dedupeConsecutivePoints([target.points[nearest.index], pointer]),
      hasMoved: false
    });
    if (target.target === 'draft') {
      onSelectObject(null);
    } else {
      onSelectObject(target.objectId);
    }
  };

  const updatePolygonCorrection = (event: any) => {
    if (!polygonCorrectionDraftRef.current) {
      return;
    }

    const pointer = getPointer(event);

    if (!pointer) {
      return;
    }

    appendPolygonCorrectionPoint(pointer);
  };

  const finishPolygonCorrection = (event: any) => {
    const correctionDraft = polygonCorrectionDraftRef.current;

    if (!correctionDraft) {
      return false;
    }

    const pointer = getPointer(event);

    if (!pointer) {
      return false;
    }

    const target = getPolygonCorrectionTarget(correctionDraft);
    const correctionPoints = dedupeConsecutivePoints([...correctionDraft.points, pointer]);

    if (!target) {
      return false;
    }

    const nearest = findNearestPolygonPoint(target.points, pointer, POLYGON_CORRECTION_HIT_SCREEN_DISTANCE / canvasScale);

    if (nearest && nearest.index !== correctionDraft.startIndex && correctionPoints.length > 1) {
      applyPolygonCorrection(correctionDraft, nearest.index, correctionPoints);
      updatePolygonCorrectionDraft(null);
      return true;
    }

    return false;
  };

  const finishPolygonDraft = () => {
    if (!hasActiveClass || polygonDraft.length < 3) {
      return;
    }

    onCreateObject({
      type: 'polygon',
      label: activeLabel,
      color: '#7CFC8A',
      source: 'manual',
      points: polygonDraft,
      area: getPolygonBounds(polygonDraft)
    });
    setPolygonDraft([]);
  };

  const startBrush = (event: any) => {
    if (!hasActiveClass) {
      return;
    }

    const pointer = getPointer(event);

    if (!pointer) {
      return;
    }

    setBrushDraft([pointer]);
    onSelectObject(null);
  };

  const updateBrush = (event: any) => {
    const pointer = getPointer(event);

    if (!pointer || brushDraft.length === 0) {
      return;
    }

    setBrushDraft((current) => [...current, pointer]);
  };

  const finishBrush = (operation: 'paint' | 'erase') => {
    if (!hasActiveClass || brushDraft.length < 2) {
      setBrushDraft([]);
      return;
    }

    const bounds = getPolygonBounds(brushDraft);
    onCreateObject({
      type: 'brush',
      label: activeLabel,
      color: '#7CFC8A',
      operation,
      source: 'manual',
      points: brushDraft,
      area: bounds
    });
    setBrushDraft([]);
  };

  const pointInObject = (object: AnnotationObject, point: PolygonPoint) => {
    if (!object.area) {
      return false;
    }

    return (
      point.x >= object.area.x &&
      point.x <= object.area.x + object.area.width &&
      point.y >= object.area.y &&
      point.y <= object.area.y + object.area.height
    );
  };

  const splitAtPoint = (event: any) => {
    const pointer = getPointer(event);

    if (!pointer || !selectedObjectId) {
      return;
    }

    const selected = visibleObjects.find((object) => object.id === selectedObjectId);

    if (selected?.type === 'box' && selected.area && pointInObject(selected, pointer)) {
      onSplitObject(selected.id, pointer.x);
    }
  };

  const stopObjectPointerEvent = (event: any) => {
    event.cancelBubble = true;
    event.evt?.stopPropagation?.();
  };

  const isPolygonCorrectionGesture = (event: any) =>
    activeTool === 'polygon' && (event.evt?.shiftKey || isShiftPressed);

  const rememberObjectMoveIntent = (object: AnnotationObject, event: any) => {
    objectMoveIntentRef.current =
      !object.locked && (event.evt?.ctrlKey || event.evt?.metaKey || isCtrlPressed) ? object.id : null;
  };

  const resetObjectDragPosition = (object: AnnotationObject, event: any) => {
    if (object.type === 'box' && object.area) {
      event.target.position({ x: object.area.x, y: object.area.y });
      return;
    }

    event.target.position({ x: 0, y: 0 });
  };

  const startObjectMoveDrag = (object: AnnotationObject, event: any) => {
    stopObjectPointerEvent(event);
    onSelectObject(object.id);

    const canMove =
      !object.locked &&
      (objectMoveIntentRef.current === object.id || event.evt?.ctrlKey || event.evt?.metaKey || isCtrlPressed);

    if (!canMove) {
      objectMoveIntentRef.current = null;
      objectMoveDragRef.current = null;
      event.target.stopDrag();
      resetObjectDragPosition(object, event);
      return;
    }

    objectMoveIntentRef.current = null;
    objectMoveDragRef.current = object.id;
  };

  const previewObjectPatch = (id: AnnotationObject['id'], patch: Partial<AnnotationObject>) => {
    setObjectEditPreview({ id, patch });
  };

  const commitObjectPatch = (id: AnnotationObject['id'], patch: Partial<AnnotationObject>) => {
    setObjectEditPreview(null);
    onUpdateObject(id, patch);
  };

  const getDraggedBoxArea = (object: AnnotationObject, event: any) => {
    if (!object.area) {
      return null;
    }

    return clampAreaToImage(
      {
        ...object.area,
        x: Math.round(event.target.x()),
        y: Math.round(event.target.y())
      },
      imageSize
    );
  };

  const previewMoveBox = (object: AnnotationObject, event: any) => {
    if (!object.area || object.locked || objectMoveDragRef.current !== object.id) {
      return;
    }

    const nextArea = getDraggedBoxArea(object, event);

    if (!nextArea) {
      return;
    }

    event.target.position({ x: nextArea.x, y: nextArea.y });
    previewObjectPatch(object.id, { area: nextArea });
  };

  const moveBox = (object: AnnotationObject, event: any) => {
    if (!object.area || object.locked || objectMoveDragRef.current !== object.id) {
      resetObjectDragPosition(object, event);
      objectMoveIntentRef.current = null;
      objectMoveDragRef.current = null;
      setObjectEditPreview(null);
      return;
    }

    const nextArea = getDraggedBoxArea(object, event);

    if (!nextArea) {
      return;
    }

    event.target.position({ x: nextArea.x, y: nextArea.y });
    objectMoveIntentRef.current = null;
    objectMoveDragRef.current = null;
    commitObjectPatch(object.id, { area: nextArea });
  };

  const resizeBox = (object: AnnotationObject, handle: BoxResizeHandle, event: any, shouldCommit: boolean) => {
    if (!object.area || object.locked) {
      return;
    }

    const pointer = getPointer(event);

    if (!pointer) {
      return;
    }

    const nextArea = resizeBoxArea(object.area, handle, pointer, imageSize);

    if (shouldCommit) {
      commitObjectPatch(object.id, { area: nextArea });
      return;
    }

    previewObjectPatch(object.id, { area: nextArea });
  };

  const movePolygon = (object: AnnotationObject, event: any) => {
    if (!object.points?.length || object.locked || objectMoveDragRef.current !== object.id) {
      resetObjectDragPosition(object, event);
      objectMoveIntentRef.current = null;
      objectMoveDragRef.current = null;
      return;
    }

    const bounds = getPolygonBounds(object.points);
    const dx = clamp(event.target.x(), -bounds.x, imageSize.width - (bounds.x + bounds.width));
    const dy = clamp(event.target.y(), -bounds.y, imageSize.height - (bounds.y + bounds.height));
    const nextPoints = object.points.map((point) => ({
      x: Math.round(point.x + dx),
      y: Math.round(point.y + dy)
    }));

    event.target.position({ x: 0, y: 0 });
    objectMoveIntentRef.current = null;
    objectMoveDragRef.current = null;
    commitObjectPatch(object.id, {
      points: nextPoints,
      area: getPolygonBounds(nextPoints)
    });
  };

  const movePolygonPoint = (object: AnnotationObject, pointIndex: number, event: any, shouldCommit: boolean) => {
    if (!object.points?.[pointIndex] || object.locked) {
      return;
    }

    const pointer = getPointer(event);

    if (!pointer) {
      return;
    }

    const nextPoints = object.points.map((point, index) =>
      index === pointIndex
        ? {
            x: Math.round(pointer.x),
            y: Math.round(pointer.y)
          }
        : point
    );
    const patch = {
      points: nextPoints,
      area: getPolygonBounds(nextPoints)
    };

    if (shouldCommit) {
      commitObjectPatch(object.id, patch);
      return;
    }

    previewObjectPatch(object.id, patch);
  };

  const renderMaskAnnotations = (items: AnnotationObject[]) => {
    const localMaskObjects = items.filter((item) => item.type === 'polygon' || item.type === 'brush');
    const paintMaskObjects = localMaskObjects.filter(
      (item) => !(item.type === 'brush' && item.operation === 'erase')
    );

    return (
      <>
        {localMaskObjects.map((object) => {
          if (!object.points) {
            return null;
          }

          if (object.type === 'brush' && object.operation === 'erase') {
            return (
              <Line
                key={object.id}
                points={object.points.flatMap((point) => [point.x, point.y])}
                stroke="#000000"
                strokeWidth={24}
                lineCap="round"
                lineJoin="round"
                tension={0.25}
                globalCompositeOperation="destination-out"
                listening={false}
              />
            );
          }

          const isSelected = selectedObjectId === object.id;
          const stroke = isSelected ? '#8cfb95' : object.color;
          const fill = object.color;
          const listedIndex = paintMaskObjects.findIndex((item) => item.id === object.id);

          if (object.type === 'polygon') {
            return (
              <Group
                key={object.id}
                draggable={!object.locked && !isPolygonCorrectionMode}
                onMouseDown={(event) => {
                  if (isPolygonCorrectionGesture(event)) {
                    stopObjectPointerEvent(event);
                    startPolygonCorrection(event, object);
                    return;
                  }

                  rememberObjectMoveIntent(object, event);
                  stopObjectPointerEvent(event);
                  onSelectObject(object.id);
                }}
                onClick={(event) => {
                  if (isPolygonCorrectionGesture(event)) {
                    stopObjectPointerEvent(event);
                    return;
                  }

                  stopObjectPointerEvent(event);
                  onSelectObject(object.id);
                }}
                onDragStart={(event) => {
                  if (isPolygonCorrectionGesture(event) || polygonCorrectionDraftRef.current) {
                    event.target.stopDrag();
                    return;
                  }

                  startObjectMoveDrag(object, event);
                }}
                onDragEnd={(event) => movePolygon(object, event)}
              >
                <Line
                  points={object.points.flatMap((point) => [point.x, point.y])}
                  closed
                  stroke={stroke}
                  strokeWidth={isSelected ? 3 : 2}
                  fill={fill}
                  opacity={getObjectOpacity(object)}
                />
                <Text
                  x={object.points[0]?.x ?? 0}
                  y={(object.points[0]?.y ?? 0) - 18}
                  text={`${listedIndex + 1} ${object.label}`}
                  fill="#152017"
                  fontSize={14}
                  padding={4}
                />
              </Group>
            );
          }

          if (object.type === 'brush') {
            return (
              <Group
                key={object.id}
                onMouseDown={(event) => {
                  rememberObjectMoveIntent(object, event);
                  stopObjectPointerEvent(event);
                  onSelectObject(object.id);
                }}
                onClick={(event) => {
                  stopObjectPointerEvent(event);
                  onSelectObject(object.id);
                }}
              >
                <Line
                  points={object.points.flatMap((point) => [point.x, point.y])}
                  stroke={stroke}
                  strokeWidth={16}
                  lineCap="round"
                  lineJoin="round"
                  opacity={getObjectOpacity(object)}
                  tension={0.25}
                  globalCompositeOperation="source-over"
                />
                <Text
                  x={object.points[0]?.x ?? 0}
                  y={(object.points[0]?.y ?? 0) - 18}
                  text={`${listedIndex + 1} ${object.label}`}
                  fill="#d8ffe2"
                  fontSize={14}
                  padding={4}
                />
              </Group>
            );
          }

          return null;
        })}
      </>
    );
  };

  const renderDetectionAnnotations = (items: AnnotationObject[]) => {
    const localDetectionObjects = items.filter((item) => item.type === 'box');
    const localListedObjects = items.filter((item) => !(item.type === 'brush' && item.operation === 'erase'));

    return (
      <>
        {localDetectionObjects.map((object, index) => {
          const isSelected = selectedObjectId === object.id;
          const stroke = isSelected ? '#8cfb95' : object.color;
          const fill = object.color;

          if (!object.area) {
            return null;
          }

          return (
            <Group key={object.id}>
              <Rect
                x={object.area.x}
                y={object.area.y}
                width={object.area.width}
                height={object.area.height}
                stroke={stroke}
                strokeWidth={isSelected ? 3 : 2}
                fill={fill}
                opacity={getObjectOpacity(object)}
                dash={isSelected ? [8, 4] : undefined}
                draggable={!object.locked}
                onMouseDown={(event) => {
                  rememberObjectMoveIntent(object, event);
                  stopObjectPointerEvent(event);
                  onSelectObject(object.id);
                }}
                onClick={(event) => {
                  stopObjectPointerEvent(event);
                  onSelectObject(object.id);
                }}
                onDragStart={(event) => {
                  startObjectMoveDrag(object, event);
                }}
                onDragMove={(event) => {
                  previewMoveBox(object, event);
                }}
                onDragEnd={(event) => {
                  moveBox(object, event);
                }}
              />
              <Text
                x={object.area.x}
                y={Math.max(0, object.area.y - 20)}
                text={`${localListedObjects.filter((item) => item.type !== 'box').length + index + 1} ${object.label}`}
                fill="#d8ffe2"
                fontSize={14}
                padding={4}
              />
            </Group>
          );
        })}
      </>
    );
  };

  return (
    <div className="flex h-[clamp(700px,calc(100vh-7rem),880px)] min-w-0 flex-col overflow-hidden rounded-[24px] border border-slate-800 bg-slate-900/95 shadow-[0_24px_80px_rgba(15,23,42,0.38)]">
      {activeTool === 'polygon' && (
        <div className="flex items-center justify-end border-b border-slate-800 bg-slate-950/90 px-5 py-3">
          <button
            type="button"
            onClick={finishPolygonDraft}
            disabled={polygonDraft.length < 3}
            className="h-9 rounded-lg bg-brand-500 px-5 text-sm font-semibold text-white transition hover:bg-brand-400 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
            title="Завершить полигон"
          >
            Done
          </button>
        </div>
      )}

      <div className="relative z-30 flex flex-wrap items-center gap-3 border-b border-slate-800 bg-slate-900 px-4 py-3 text-slate-300">
        <div className="flex items-center gap-2">
          <button
            ref={menuButtonRef}
            type="button"
            onClick={onToggleMenu}
            className={`rounded-lg border px-3 py-1.5 text-xs font-medium ${
              isMenuOpen
                ? 'border-brand-500/40 bg-brand-500/10 text-brand-100'
                : 'border-slate-700 bg-slate-950 text-slate-100'
            }`}
          >
            Menu
          </button>
          <button type="button" onClick={onSave} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs">
            Save
          </button>
          <button
            type="button"
            disabled={!canUndo}
            onClick={onUndo}
            className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs disabled:cursor-not-allowed disabled:opacity-40"
          >
            Undo
          </button>
          <button
            type="button"
            disabled={!canRedo}
            onClick={onRedo}
            className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs disabled:cursor-not-allowed disabled:opacity-40"
          >
            Redo
          </button>
        </div>

        <div className="flex flex-1 items-center gap-3">
          <div className="flex gap-1 text-lg">
            <button type="button" onClick={onFirstImage} className="rounded px-1 hover:bg-slate-800" title="Первое изображение">&#9198;</button>
            <button type="button" onClick={onPreviousImage} className="rounded px-1 hover:bg-slate-800" title="Предыдущее изображение">&#9664;</button>
            <button type="button" onClick={onNextImage} className="rounded px-1 hover:bg-slate-800" title="Следующее изображение">&#9654;</button>
            <button type="button" onClick={onLastImage} className="rounded px-1 hover:bg-slate-800" title="Последнее изображение">&#9197;</button>
          </div>

          <input
            type="range"
            min={0}
            max={Math.max(0, imageCount - 1)}
            value={imageIndex}
            onChange={(event) => onSelectImageByIndex(Number(event.target.value))}
            className="h-2 flex-1 cursor-pointer appearance-none rounded-full bg-slate-800 accent-brand-500"
          />

          <input
            value={indexInput}
            onChange={(event) => setIndexInput(event.target.value)}
            onBlur={() => {
              const parsed = Number(indexInput);
              if (!Number.isNaN(parsed)) {
                onSelectImageByIndex(clamp(parsed - 1, 0, imageCount - 1));
              } else {
                setIndexInput(String(imageIndex + 1));
              }
            }}
            className="w-16 rounded-lg border border-slate-700 bg-slate-950 px-2 py-1 text-center text-xs text-slate-100"
          />
        </div>

        <button
          type="button"
          onClick={onOpenImagePicker}
          className="rounded-full border border-slate-700 bg-slate-950 px-3 py-1 text-xs text-slate-200 transition hover:border-brand-500/40 hover:text-white"
        >
          {imageName}
        </button>

        {isMenuOpen && (
          <div
            ref={menuRef}
            className="absolute left-4 top-[calc(100%+0.5rem)] z-50 w-64 rounded-2xl border border-slate-700 bg-slate-950 p-3 shadow-2xl"
          >
            <div className="mb-2 text-xs uppercase tracking-[0.22em] text-slate-500">Workspace Menu</div>
            <div className="space-y-2">
              <button type="button" onClick={onOpenImagePicker} className="w-full rounded-xl border border-slate-800 bg-slate-900 px-3 py-2 text-left text-sm text-slate-200">
                Добавить изображения
              </button>
              <button
                type="button"
                onClick={onLoadSaved}
                disabled={!hasSavedDraft}
                className="w-full rounded-xl border border-slate-800 bg-slate-900 px-3 py-2 text-left text-sm text-slate-200 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Загрузить сохранённый черновик
              </button>
              <button type="button" onClick={onExportProject} className="w-full rounded-xl border border-slate-800 bg-slate-900 px-3 py-2 text-left text-sm text-slate-200">
                Экспортировать проект
              </button>
              <button type="button" onClick={onResetAnnotations} className="w-full rounded-xl border border-rose-500/20 bg-rose-500/10 px-3 py-2 text-left text-sm text-rose-100">
                Очистить аннотации текущего изображения
              </button>
              <button
                type="button"
                onClick={() => {
                  setZoom(1);
                  setOffset({ x: 0, y: 0 });
                  onCloseMenu();
                }}
                className="w-full rounded-xl border border-slate-800 bg-slate-900 px-3 py-2 text-left text-sm text-slate-200"
              >
                Сбросить zoom и pan
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-[62px_minmax(0,1fr)] overflow-hidden rounded-b-[24px]">
        <div className="border-r border-slate-800 bg-slate-950/95 py-4">
          <div className="flex flex-col items-center gap-3">
            {[
              { id: 'box' as ToolMode, icon: '▭', label: 'Box', hint: 'Создание прямоугольной области на изображении.' },
              { id: 'polygon' as ToolMode, icon: '⬠', label: 'Polygon', hint: 'Клики ставят точки. Shift подсвечивает точки; клик-точка, ведение, клик-точка заменяет участок.' }
            ].map((tool) => {
              const isActive = activeTool === tool.id;

              return (
                <div key={tool.id} className="group relative flex justify-center">
                  <button
                    type="button"
                    onClick={() => onToolChange(activeTool === tool.id ? null : tool.id)}
                    disabled={!hasActiveClass}
                    className={`flex h-10 w-10 items-center justify-center rounded-xl border text-sm ${
                      !hasActiveClass
                        ? 'cursor-not-allowed border-slate-800 bg-slate-950 text-slate-600'
                        : isActive
                        ? 'border-brand-500/40 bg-brand-500/15 text-brand-100'
                        : 'border-slate-800 bg-slate-900 text-slate-300'
                    }`}
                    aria-label={hasActiveClass ? tool.label : `${tool.label}: сначала добавьте класс`}
                    title={hasActiveClass ? tool.label : 'Сначала добавьте класс'}
                  >
                    {tool.icon}
                  </button>

                  <div className="pointer-events-none absolute left-[calc(100%+0.75rem)] top-1/2 z-30 w-52 -translate-y-1/2 rounded-xl border border-slate-700 bg-slate-950/95 px-3 py-2 text-left opacity-0 shadow-xl transition duration-150 group-hover:opacity-100">
                    <div className="text-xs font-semibold text-white">{tool.label}</div>
                    <div className="mt-1 text-[11px] leading-4 text-slate-400">{tool.hint}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="grid min-h-0 grid-cols-[minmax(0,1fr)_292px]">
          <div className="min-h-0 overflow-hidden bg-slate-900 p-3">
            <div
              ref={containerRef}
              className="relative flex h-full min-h-0 items-center justify-center overflow-hidden rounded-[18px] border border-slate-800 bg-slate-950"
            >
              <Stage
                width={stageWidth}
                height={stageHeight}
                onContextMenu={(event) => event.evt.preventDefault()}
                onMouseDown={(event) => {
                  if (event.evt.button === 0) {
                    leftButtonDownRef.current = true;
                  }

                  if (event.evt.ctrlKey || event.evt.metaKey || event.evt.button !== 0) {
                    startCanvasPan(event);
                    return;
                  }

                  if (activeTool === 'box') {
                    startBox(event);
                    return;
                  }

                  if (activeTool === 'polygon') {
                    if (polygonCorrectionDraftRef.current) {
                      finishPolygonCorrection(event);
                      return;
                    }

                    if (event.evt.shiftKey || isShiftPressed) {
                      startPolygonCorrection(event);
                      return;
                    }

                    pendingPolygonClickRef.current = getPointer(event);
                    startCanvasPan(event, false);
                    return;
                  }

                  if (!activeTool) {
                    startCanvasPan(event);
                  }
                }}
                onMouseMove={(event) => {
                  if (activeTool === 'polygon') {
                    if (polygonCorrectionDraftRef.current) {
                      updatePolygonCorrection(event);
                      return;
                    }

                    if (pendingPolygonClickRef.current) {
                      updateCanvasPan(event);
                    }

                    return;
                  }

                  if (panStartRef.current) {
                    updateCanvasPan(event);
                    return;
                  }

                  if (activeTool === 'box') {
                    updateBox(event);
                  }
                }}
                onMouseUp={(event) => {
                  leftButtonDownRef.current = false;

                  if (activeTool === 'polygon') {
                    const correctionDraft = polygonCorrectionDraftRef.current;

                    if (correctionDraft?.hasMoved) {
                      const didFinish = finishPolygonCorrection(event);

                      if (!didFinish) {
                        updatePolygonCorrectionDraft(null);
                      }
                    }

                    if (pendingPolygonClickRef.current) {
                      if (!hasDraggedCanvasRef.current) {
                        addPolygonPoint(event);
                      }

                      pendingPolygonClickRef.current = null;
                      stopCanvasPan();
                    }
                  }

                  if (activeTool === 'box') {
                    finishBox();
                  }

                  stopCanvasPan();
                }}
                onWheel={(event) => {
                  event.evt.preventDefault();

                  const pointer = event.target.getStage()?.getPointerPosition();

                  if (!pointer) {
                    return;
                  }

                  zoomAtPointer(pointer.x, pointer.y, event.evt.deltaY < 0 ? 1 : -1);
                }}
              >
                <Layer x={offset.x} y={offset.y} scaleX={canvasScale} scaleY={canvasScale}>
                  <Rect x={0} y={0} width={imageSize.width} height={imageSize.height} fill="#0f172a" listening={false} />
                  {image && <KonvaImage image={image} width={imageSize.width} height={imageSize.height} listening={false} />}
                </Layer>

                <Layer x={offset.x} y={offset.y} scaleX={canvasScale} scaleY={canvasScale}>
                  {compareViewMode === 'split' ? (
                    <>
                      <Group clipX={0} clipY={0} clipWidth={imageSize.width / 2} clipHeight={imageSize.height}>
                        {renderMaskAnnotations(comparisonLeftObjects)}
                      </Group>
                      <Group
                        clipX={imageSize.width / 2}
                        clipY={0}
                        clipWidth={imageSize.width / 2}
                        clipHeight={imageSize.height}
                      >
                        {renderMaskAnnotations(comparisonRightObjects)}
                      </Group>
                    </>
                  ) : (
                    renderMaskAnnotations(previewVisibleObjects)
                  )}
                </Layer>

                <Layer x={offset.x} y={offset.y} scaleX={canvasScale} scaleY={canvasScale}>
                  {compareViewMode === 'split' ? (
                    <>
                      <Group clipX={0} clipY={0} clipWidth={imageSize.width / 2} clipHeight={imageSize.height}>
                        {renderDetectionAnnotations(comparisonLeftObjects)}
                      </Group>
                      <Group
                        clipX={imageSize.width / 2}
                        clipY={0}
                        clipWidth={imageSize.width / 2}
                        clipHeight={imageSize.height}
                      >
                        {renderDetectionAnnotations(comparisonRightObjects)}
                      </Group>
                      <Line
                        points={[imageSize.width / 2, 0, imageSize.width / 2, imageSize.height]}
                        stroke="#f8fafc"
                        strokeWidth={2}
                        dash={[10, 8]}
                        opacity={0.8}
                      />
                      <Text x={24} y={20} text={compareLeftSource} fill="#f8fafc" fontSize={18} padding={6} />
                      <Text
                        x={imageSize.width / 2 + 24}
                        y={20}
                        text={compareRightSource}
                        fill="#f8fafc"
                        fontSize={18}
                        padding={6}
                      />
                    </>
                  ) : (
                    renderDetectionAnnotations(previewVisibleObjects)
                  )}
                </Layer>

                <Layer x={offset.x} y={offset.y} scaleX={canvasScale} scaleY={canvasScale}>
                  {selectedObject?.type === 'box' && !selectedObject.locked && selectedObject.area && (
                    <>
                      {getBoxResizeHandles(selectedObject.area).map((handle) => (
                        <Rect
                          key={`${selectedObject.id}-${handle.id}`}
                          x={handle.x - RESIZE_HANDLE_SIZE / canvasScale / 2}
                          y={handle.y - RESIZE_HANDLE_SIZE / canvasScale / 2}
                          width={RESIZE_HANDLE_SIZE / canvasScale}
                          height={RESIZE_HANDLE_SIZE / canvasScale}
                          fill="#f8fafc"
                          stroke="#16a34a"
                          strokeWidth={2 / canvasScale}
                          draggable
                          onMouseDown={(event) => {
                            stopObjectPointerEvent(event);
                            onSelectObject(selectedObject.id);
                          }}
                          onClick={stopObjectPointerEvent}
                          onDragMove={(event) => resizeBox(selectedObject, handle.id, event, false)}
                          onDragEnd={(event) => resizeBox(selectedObject, handle.id, event, true)}
                        />
                      ))}
                    </>
                  )}

                  {selectedObject?.type === 'polygon' &&
                    !selectedObject.locked &&
                    !isPolygonCorrectionMode &&
                    selectedObject.points?.map((point, index) => (
                      <Circle
                        key={`${selectedObject.id}-point-${index}`}
                        x={point.x}
                        y={point.y}
                        radius={7 / canvasScale}
                        fill="#f8fafc"
                        stroke="#16a34a"
                        strokeWidth={2 / canvasScale}
                        draggable
                        onMouseDown={(event) => {
                          stopObjectPointerEvent(event);
                          onSelectObject(selectedObject.id);
                        }}
                        onClick={stopObjectPointerEvent}
                        onDragMove={(event) => movePolygonPoint(selectedObject, index, event, false)}
                        onDragEnd={(event) => movePolygonPoint(selectedObject, index, event, true)}
                      />
                    ))}

                  {draftBox && (
                    <Rect
                      x={draftBox.x}
                      y={draftBox.y}
                      width={draftBox.width}
                      height={draftBox.height}
                      stroke="#52b5ff"
                      strokeWidth={2}
                      dash={[7, 5]}
                      fill="rgba(82, 181, 255, 0.12)"
                    />
                  )}

                  {selectedPolygonObject?.points &&
                    !selectedPolygonObject.locked &&
                    polygonDraft.length === 0 &&
                    (isShiftPressed ||
                      (polygonCorrectionDraft?.target === 'object' &&
                        polygonCorrectionDraft.objectId === selectedPolygonObject.id)) &&
                    selectedPolygonObject.points.map((point, index) => (
                      <Circle
                        key={`${selectedPolygonObject.id}-handle-${index}`}
                        x={point.x}
                        y={point.y}
                        radius={9 / canvasScale}
                        fill="#7CFC8A"
                        stroke="#14532d"
                        strokeWidth={2.5 / canvasScale}
                        listening={false}
                      />
                    ))}

                  {polygonDraft.length > 0 && (
                    <>
                      <Line points={polygonDraft.flatMap((point) => [point.x, point.y])} stroke="#52b5ff" strokeWidth={2} />
                      {polygonDraft.map((point, index) => (
                        <Circle
                          key={`${point.x}-${point.y}-${index}`}
                          x={point.x}
                          y={point.y}
                          radius={isPolygonCorrectionMode ? 9 / canvasScale : 4}
                          fill={isPolygonCorrectionMode ? '#7CFC8A' : '#52b5ff'}
                          stroke={isPolygonCorrectionMode ? '#14532d' : undefined}
                          strokeWidth={isPolygonCorrectionMode ? 2.5 / canvasScale : 0}
                        />
                      ))}
                    </>
                  )}

                  {polygonCorrectionDraft && (
                    <>
                      <Line
                        points={polygonCorrectionDraft.points.flatMap((point) => [point.x, point.y])}
                        stroke="#f8fafc"
                        strokeWidth={2}
                        dash={[6, 6]}
                      />
                      {polygonCorrectionDraft.points.map((point, index) => (
                        <Circle
                          key={`correction-${point.x}-${point.y}-${index}`}
                          x={point.x}
                          y={point.y}
                          radius={3.5}
                          fill="#f8fafc"
                          stroke="#334155"
                          strokeWidth={1}
                        />
                      ))}
                    </>
                  )}

                </Layer>
              </Stage>

              <div className="pointer-events-none absolute inset-x-4 bottom-4 rounded-lg bg-[rgba(22,22,22,0.76)] px-4 py-2 text-xs text-white">
                {!imageSrc && 'В проекте пока нет изображения. Добавьте файл через меню или страницу загрузки.'}
                {imageSrc && activeTool === 'box' && 'Протяните мышью, чтобы создать прямоугольник. Колесо меняет масштаб. Ctrl/Cmd + протяжка по объекту перемещает его.'}
                {imageSrc && activeTool === 'polygon' && 'Кликайте по контуру объекта. Shift исправляет точки. Колесо меняет масштаб. Ctrl/Cmd + протяжка по объекту перемещает его.'}
                {imageSrc && !activeTool && 'Колесо мыши меняет масштаб. Перетяните пустую область, чтобы сдвинуть изображение. Ctrl/Cmd + протяжка по объекту перемещает его.'}
              </div>
            </div>
          </div>

          <aside className="flex max-h-full min-h-0 flex-col gap-2 overflow-y-auto border-l border-slate-800 bg-slate-950/80 p-2 custom-scroll">
            <section className="shrink-0 overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/90 shadow-[inset_0_1px_0_rgba(148,163,184,0.06)]">
              <div className="border-b border-slate-800 bg-slate-950/80 px-4 py-3">
                <div className="flex items-center justify-between text-sm font-semibold text-slate-100">
                  <span>Список объектов</span>
                  <span className="rounded-full border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-300">{listedObjects.length}</span>
                </div>
              </div>

              <div className="max-h-[160px] overflow-y-auto p-2 custom-scroll">
                {listedObjects.map((object, index) => {
                  const isSelected = selectedObjectId === object.id;
                  const isLocked = Boolean(object.locked);

                  return (
                    <div
                      key={object.id}
                      className={`mb-2 rounded-xl border ${
                        isSelected ? 'border-brand-500/50 bg-brand-500/10' : 'border-slate-700/70 bg-slate-950/85'
                      }`}
                    >
                      <div className="space-y-2.5 px-3 py-3">
                        <button type="button" onClick={() => onSelectObject(object.id)} className="w-full min-w-0 bg-transparent text-left">
                          <div className="flex min-w-0 items-start gap-2">
                            <span className="mt-0.5 shrink-0 text-[11px] uppercase tracking-[0.14em] text-slate-500">{index + 1}</span>
                            <span className="min-w-0 break-words text-sm font-medium leading-5 text-slate-100">{object.label}</span>
                          </div>
                          <div className="mt-1 pl-6 text-xs leading-5 text-slate-400">
                            {isLocked && 'Заблокирован · '}
                            {object.source === 'imported' && 'Импорт из аннотаций'}
                            {object.source === 'model' && `${object.modelName ?? 'Модель'}${object.score ? ` · ${Math.round(object.score * 100)}%` : ''}`}
                            {object.source === 'manual' && object.type === 'brush' && object.operation === 'paint' && 'Ручная маска'}
                            {object.source === 'manual' && object.type !== 'brush' && 'Ручная разметка'}
                          </div>
                        </button>
                        <div className="flex min-w-0 items-center gap-2 pl-6">
                          <select
                            value={object.label}
                            onClick={(event) => event.stopPropagation()}
                            onMouseDown={(event) => event.stopPropagation()}
                            onChange={(event) => {
                              onSelectObject(object.id);
                              updateObjectClass(object, event.target.value);
                            }}
                            disabled={isLocked || !classList.length}
                            className="h-9 min-w-0 flex-1 rounded-lg border border-slate-700 bg-slate-950 px-3 text-xs font-medium text-slate-100 outline-none transition focus:border-brand-500 disabled:cursor-not-allowed disabled:opacity-50"
                            aria-label={`Заменить класс объекта ${index + 1}`}
                            title={isLocked ? 'Разблокируйте объект, чтобы заменить класс' : 'Заменить класс'}
                          >
                            {!classList.some((item) => item.name === object.label) && (
                              <option value={object.label}>{object.label}</option>
                            )}
                            {classList.map((item) => (
                              <option key={item.name} value={item.name}>
                                {item.name}
                              </option>
                            ))}
                          </select>
                          <button
                            type="button"
                            onClick={() => toggleObjectLock(object)}
                            className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border transition ${
                              isLocked
                                ? 'border-amber-400/40 bg-amber-400/10 text-amber-200 hover:border-amber-300/60 hover:bg-amber-400/15'
                                : 'border-slate-700 bg-slate-900/80 text-slate-400 hover:border-brand-500/50 hover:bg-brand-500/10 hover:text-brand-100'
                            }`}
                            aria-label={isLocked ? `Разблокировать объект ${index + 1}` : `Заблокировать объект ${index + 1}`}
                            title={isLocked ? 'Разблокировать объект' : 'Заблокировать объект'}
                          >
                            {isLocked ? <Lock size={15} aria-hidden="true" /> : <Unlock size={15} aria-hidden="true" />}
                          </button>
                          <button
                            type="button"
                            onClick={() => onDeleteObject(object.id)}
                            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-slate-700 bg-slate-900/80 text-slate-400 transition hover:border-rose-500/50 hover:bg-rose-500/10 hover:text-rose-200"
                            aria-label={`Удалить объект ${index + 1}`}
                            title="Удалить объект"
                          >
                            <Trash2 size={15} aria-hidden="true" />
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>

            <section className="shrink-0 rounded-2xl border border-slate-800 bg-slate-900/90 px-4 py-3 shadow-[inset_0_1px_0_rgba(148,163,184,0.06)]">
              <div className="text-sm font-semibold text-slate-100">Настройки</div>
              <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-slate-400">
                <div className="truncate">
                  Активный класс: <span className="font-semibold text-slate-100">{activeLabel || 'Нет классов'}</span>
                </div>
                <div className="truncate">
                  Масштаб: <span className="font-semibold text-slate-100">{zoom.toFixed(2)}x</span>
                </div>
              </div>
              <label className="mt-2 block text-xs text-slate-400">
                Класс объекта
                <select
                  value={selectedObject?.label ?? ''}
                  onChange={(event) => {
                    if (selectedObject) {
                      updateObjectClass(selectedObject, event.target.value);
                    }
                  }}
                  disabled={!selectedObject || selectedObject.locked}
                  className="mt-1.5 w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-xs text-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <option value="" disabled>
                    Выберите объект
                  </option>
                  {classList.map((item) => (
                    <option key={item.name} value={item.name}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </label>
              <div className="mt-2 flex rounded-xl border border-slate-800 bg-slate-950 p-1">
                {(['class', 'object'] as const).map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => onOpacityTargetModeChange(mode)}
                    className={`flex-1 rounded-lg px-2 py-1.5 text-xs font-semibold transition ${
                      opacityTargetMode === mode ? 'bg-brand-500 text-white' : 'bg-transparent text-slate-400 hover:text-white'
                    }`}
                  >
                    {mode === 'class' ? 'Класс' : 'Объект'}
                  </button>
                ))}
              </div>
              {opacityTargetMode === 'class' && (
                <select
                  value={selectedOpacityClass?.name ?? ''}
                  onChange={(event) => onOpacityClassNameChange(event.target.value)}
                  disabled={!classList.length}
                  className="mt-2 w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-xs text-slate-100"
                >
                  {!classList.length && <option value="">Нет классов</option>}
                  {classList.map((item) => (
                    <option key={item.name} value={item.name}>
                      {item.name}
                    </option>
                  ))}
                </select>
              )}
              {opacityTargetMode === 'object' && (
                <div className="mt-2 rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-xs text-slate-300">
                  {selectedObject ? `Объект: ${selectedObject.label}${selectedObject.locked ? ' · заблокирован' : ''}` : 'Выберите объект'}
                </div>
              )}
              <div className="mt-2">
                <div className="mb-2 flex items-center justify-between text-xs text-slate-500">
                  <span>Прозрачность</span>
                  <span className="text-slate-300">{Math.round(currentOpacity * 100)}%</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={Math.round(currentOpacity * 100)}
                  onChange={(event) => updateCurrentOpacity(Number(event.target.value) / 100)}
                  disabled={opacityTargetMode === 'object' && (!selectedObject || selectedObject.locked)}
                  className="w-full accent-brand-500 disabled:cursor-not-allowed disabled:opacity-50"
                />
              </div>
            </section>

            <section className="shrink-0 rounded-2xl border border-slate-800 bg-slate-900/90 px-4 py-3 shadow-[inset_0_1px_0_rgba(148,163,184,0.06)]">
              <div className="mb-3 flex items-center justify-between gap-2">
                <div>
                  <div className="text-sm font-semibold text-slate-100">Классы</div>
                  <div className="text-[11px] text-slate-500">{getClassCountLabel(classList.length)}</div>
                </div>
              </div>

              <div className="mt-3 max-h-[220px] space-y-2 overflow-y-auto pr-1 custom-scroll">
                {!classList.length && (
                  <div className="rounded-xl border border-dashed border-slate-800 bg-slate-950 px-3 py-3 text-sm text-slate-500">
                    Нет классов
                  </div>
                )}
                {classList.map((item) => (
                  <div
                    key={item.name}
                    className={`flex items-center justify-between gap-2 rounded-xl border px-3 py-2 ${
                      activeLabel === item.name ? 'border-brand-500 bg-brand-500/10' : 'border-slate-800 bg-slate-950'
                    }`}
                  >
                    <button type="button" onClick={() => onSelectClass(item.name)} className="min-w-0 flex-1 bg-transparent text-left">
                      <span className="flex items-center gap-2">
                        <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: item.color }} />
                        <span className="truncate text-sm font-medium text-white">{item.name}</span>
                      </span>
                    </button>
                    <button
                      type="button"
                      onClick={() => onToggleClassVisibility(item.name)}
                      className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] ${
                        item.visible ? 'bg-emerald-500/15 text-emerald-300' : 'bg-slate-800 text-slate-400'
                      }`}
                    >
                      {item.visible ? 'Виден' : 'Скрыт'}
                    </button>
                    <button
                      type="button"
                      onClick={() => onDeleteClass(item.name)}
                      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-slate-800 bg-slate-900/80 text-slate-400 transition hover:border-rose-500/50 hover:bg-rose-500/10 hover:text-rose-200"
                      aria-label={`Удалить класс ${item.name}`}
                      title="Удалить класс"
                    >
                      <Trash2 size={14} aria-hidden="true" />
                    </button>
                  </div>
                ))}
              </div>

              <div className="mt-3 flex gap-2">
                <input
                  value={newClassName}
                  onChange={(event) => onNewClassNameChange(event.target.value)}
                  placeholder="Новый класс"
                  className="min-w-0 flex-1 rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-white"
                />
                <button type="button" onClick={onAddClass} className="rounded-xl bg-brand-500 px-3 py-2 text-sm font-semibold text-white">
                  +
                </button>
              </div>

              <details className="group mt-3 rounded-xl border border-slate-800 bg-slate-950">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-2 text-sm font-semibold text-slate-100">
                  <span className="flex min-w-0 items-center gap-2">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-brand-500/15 text-brand-100">
                      <Wand2 size={15} />
                    </span>
                    <span className="truncate">Анализ моделями</span>
                  </span>
                  <ChevronDown size={16} className="shrink-0 text-slate-400 transition group-open:rotate-180" />
                </summary>

                <div className="border-t border-slate-800 px-3 pb-3 pt-2">
                  <div className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Классы</div>
                  <div className="mt-2 grid gap-1.5">
                    {!classList.length && <div className="rounded-lg bg-slate-900/70 px-2.5 py-2 text-xs text-slate-500">Нет классов</div>}
                    {classList.map((item) => {
                      const isChecked = analysisClassNames.includes(item.name);

                      return (
                        <label
                          key={item.name}
                          className="flex cursor-pointer items-center gap-2 rounded-lg border border-slate-800 bg-slate-900/70 px-2.5 py-2 text-xs text-slate-200"
                        >
                          <input
                            type="checkbox"
                            checked={isChecked}
                            onChange={() => onToggleAnalysisClass(item.name)}
                            className="h-4 w-4 rounded border-slate-700 bg-slate-950 accent-brand-500"
                          />
                          <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: item.color }} />
                          <span className="min-w-0 truncate">{item.name}</span>
                        </label>
                      );
                    })}
                  </div>

                  <div className="mt-3 text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Сегментация</div>
                  {renderModelOptions(
                    standardSegmentationModels,
                    selectedSegmentationModels,
                    'segmentation',
                    'h-4 w-4 rounded border-slate-700 bg-slate-950 accent-emerald-500',
                    'ml-auto shrink-0 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] text-emerald-200',
                    'Нет доступных моделей сегментации'
                  )}

                  <div className="mt-3 text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">SAHI сегментация</div>
                  {renderModelOptions(
                    sahiSegmentationModels,
                    selectedSegmentationModels,
                    'segmentation',
                    'h-4 w-4 rounded border-slate-700 bg-slate-950 accent-emerald-500',
                    'ml-auto shrink-0 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] text-emerald-200',
                    'Нет доступных SAHI моделей сегментации'
                  )}

                  <div className="mt-3 text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Детекция</div>
                  {renderModelOptions(
                    standardDetectionModels,
                    selectedDetectionModels,
                    'detection',
                    'h-4 w-4 rounded border-slate-700 bg-slate-950 accent-brand-500',
                    'ml-auto shrink-0 rounded-full bg-brand-500/10 px-2 py-0.5 text-[10px] text-brand-100',
                    'Нет доступных моделей детекции'
                  )}

                  <div className="mt-3 text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">SAHI детекция</div>
                  {renderModelOptions(
                    sahiDetectionModels,
                    selectedDetectionModels,
                    'detection',
                    'h-4 w-4 rounded border-slate-700 bg-slate-950 accent-brand-500',
                    'ml-auto shrink-0 rounded-full bg-brand-500/10 px-2 py-0.5 text-[10px] text-brand-100',
                    'Нет доступных SAHI моделей детекции'
                  )}

                  <button
                    type="button"
                    onClick={onRunModels}
                    disabled={isRunningModels}
                    className="mt-3 w-full rounded-xl bg-brand-500 px-3 py-2 text-sm font-semibold text-white transition hover:bg-brand-400 disabled:cursor-wait disabled:opacity-60"
                  >
                    {isRunningModels ? 'Отправляем на анализ...' : 'Отправить на анализ'}
                  </button>
                </div>
              </details>
            </section>
          </aside>
        </div>
      </div>
    </div>
  );
};

export default WorkspaceCanvas;
