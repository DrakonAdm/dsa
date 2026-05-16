import { useState, useEffect } from 'react';
import { ChevronDown } from 'lucide-react';

interface Model {
  name: string;
  status: string;
}

interface ModelPanelProps {
  selectedSegmentationModel: string | null;
  selectedDetectionModel: string | null;
  onSegmentationModelSelect: (model: string) => void;
  onDetectionModelSelect: (model: string) => void;
  onRunSegmentation: () => void;
}

const ModelPanel: React.FC<ModelPanelProps> = ({
  selectedSegmentationModel,
  selectedDetectionModel,
  onSegmentationModelSelect,
  onDetectionModelSelect,
  onRunSegmentation
}) => {
  const [segOpen, setSegOpen] = useState(false);
  const [detOpen, setDetOpen] = useState(false);
  const [segmentationModels, setSegmentationModels] = useState<Model[]>([]);
  const [detectionModels, setDetectionModels] = useState<Model[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchModels = async () => {
      try {
        const response = await fetch('/api/models');
        const data = await response.json();
        setSegmentationModels(data.segmentation || []);
        setDetectionModels(data.detection || []);
      } catch (error) {
        console.error('Failed to fetch models:', error);
        // Fallback to default models
        setSegmentationModels([
          { name: 'SAM2', status: 'active' },
          { name: 'SegmentAnything', status: 'idle' }
        ]);
        setDetectionModels([
          { name: 'YOLO-World', status: 'active' },
          { name: 'GroundingDino', status: 'idle' }
        ]);
      } finally {
        setLoading(false);
      }
    };

    fetchModels();
  }, []);

  if (loading) {
    return (
      <div className="rounded-3xl border border-slate-800 bg-slate-900/80 p-5">
        <div className="text-center text-slate-400">Загрузка моделей...</div>
      </div>
    );
  }

  return (
    <div className="rounded-3xl border border-slate-800 bg-slate-900/80 p-5">
      <div className="mb-5">
        <h3 className="text-lg font-semibold text-white">Модели</h3>
        <p className="text-sm text-slate-400">Выберите модель для сегментации или детекции.</p>
      </div>

      {/* Segmentation Models */}
      <div className="mb-4">
        <button
          onClick={() => setSegOpen(!segOpen)}
          className="flex w-full items-center justify-between rounded-3xl border border-slate-800 bg-slate-950 p-4 text-left"
        >
          <span className="text-white">Сегментация</span>
          <ChevronDown className={`transition ${segOpen ? 'rotate-180' : ''}`} />
        </button>
        {segOpen && (
          <div className="mt-2 space-y-2">
            {segmentationModels.map((model) => (
              <div 
                key={model.name} 
                className={`flex items-center justify-between rounded-3xl border p-3 cursor-pointer transition ${
                  selectedSegmentationModel === model.name 
                    ? 'border-brand-500 bg-brand-500/10' 
                    : 'border-slate-800 bg-slate-950/90 hover:bg-slate-800'
                }`}
                onClick={() => onSegmentationModelSelect(model.name)}
              >
                <span className="text-slate-200">{model.name}</span>
                <span className={`rounded-full px-2 py-1 text-xs ${model.status === 'active' ? 'bg-emerald-500/15 text-emerald-300' : 'bg-slate-800 text-slate-400'}`}>
                  {model.status}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Detection Models */}
      <div>
        <button
          onClick={() => setDetOpen(!detOpen)}
          className="flex w-full items-center justify-between rounded-3xl border border-slate-800 bg-slate-950 p-4 text-left"
        >
          <span className="text-white">Детекция</span>
          <ChevronDown className={`transition ${detOpen ? 'rotate-180' : ''}`} />
        </button>
        {detOpen && (
          <div className="mt-2 space-y-2">
            {detectionModels.map((model) => (
              <div 
                key={model.name} 
                className={`flex items-center justify-between rounded-3xl border p-3 cursor-pointer transition ${
                  selectedDetectionModel === model.name 
                    ? 'border-brand-500 bg-brand-500/10' 
                    : 'border-slate-800 bg-slate-950/90 hover:bg-slate-800'
                }`}
                onClick={() => onDetectionModelSelect(model.name)}
              >
                <span className="text-slate-200">{model.name}</span>
                <span className={`rounded-full px-2 py-1 text-xs ${model.status === 'active' ? 'bg-emerald-500/15 text-emerald-300' : 'bg-slate-800 text-slate-400'}`}>
                  {model.status}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {selectedSegmentationModel && (
        <button
          onClick={onRunSegmentation}
          className="w-full rounded-3xl bg-brand-500 py-3 text-white hover:bg-brand-700 transition"
        >
          Запустить сегментацию
        </button>
      )}
    </div>
  );
};

export default ModelPanel;
