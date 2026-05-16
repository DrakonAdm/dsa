import { motion } from 'framer-motion';
import { ChangeEvent, useEffect, useRef, useState } from 'react';
import PageTransition from '../components/PageTransition';
import { api, type Project } from '../lib/api';

const uploadLimits = [
  { label: 'Макс. размер файла', value: '50 МБ' },
  { label: 'Поддерживаемые форматы', value: 'JPG, PNG' },
  { label: 'TIFF', value: 'только Pro' },
  { label: 'Остаток кадров', value: '120' }
];

const UploadPage = () => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState('');
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [status, setStatus] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api
      .listProjects()
      .then((items) => {
        setProjects(items);
        setSelectedProjectId(items[0]?.id ?? '');
      })
      .catch((err) => setStatus(err instanceof Error ? err.message : 'Не удалось загрузить проекты.'));
  }, []);

  const handleFiles = (event: ChangeEvent<HTMLInputElement>) => {
    setSelectedFiles(Array.from(event.target.files ?? []));
    setStatus('');
  };

  const handleUpload = async () => {
    if (!selectedProjectId) {
      setStatus('Сначала создайте или выберите проект.');
      return;
    }

    if (selectedFiles.length === 0) {
      fileInputRef.current?.click();
      return;
    }

    setIsUploading(true);
    try {
      const uploaded = await api.uploadImages(selectedProjectId, selectedFiles);
      setStatus(`Загружено файлов: ${uploaded.length}`);
      setSelectedFiles([]);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    } catch (err) {
      setStatus(err instanceof Error ? err.message : 'Не удалось загрузить файлы.');
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <PageTransition>
      <div className="mx-auto max-w-[1400px]">
        <section className="space-y-6">
          <motion.div
            className="rounded-[2rem] border border-slate-800 bg-slate-900/80 p-6"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <h1 className="text-3xl font-semibold text-white">Загрузка датасета</h1>
            <p className="mt-2 text-slate-400">Выберите проект и отправьте изображения в backend.</p>
            <div className="mt-6">
              <select
                value={selectedProjectId}
                onChange={(event) => setSelectedProjectId(event.target.value)}
                className="w-full rounded-3xl border border-slate-800 bg-slate-950 px-4 py-3 text-slate-100 outline-none transition focus:border-brand-500"
              >
                <option value="">Проект не выбран</option>
                {projects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                  </option>
                ))}
              </select>
            </div>
            <motion.div
              className="mt-8 rounded-[2rem] border-2 border-dashed border-slate-700 bg-slate-950/90 p-10 text-center text-slate-400"
              whileHover={{ scale: 1.02, borderColor: '#eab308' }}
            >
              <input ref={fileInputRef} type="file" accept="image/png,image/jpeg" multiple onChange={handleFiles} className="hidden" />
              <div className="mb-4 text-xl font-semibold text-white">
                {selectedFiles.length ? `Выбрано файлов: ${selectedFiles.length}` : 'Выберите изображения'}
              </div>
              <p>Поддержка JPG, PNG. TIFF доступен при оформлении подписки.</p>
              <div className="mt-6 flex flex-col items-center justify-center gap-3 sm:flex-row">
                <motion.button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="rounded-3xl border border-slate-700 px-6 py-3 text-sm font-semibold text-white transition hover:border-brand-500"
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                >
                  Выбрать файлы
                </motion.button>
                <motion.button
                  type="button"
                  onClick={handleUpload}
                  disabled={isUploading}
                  className="rounded-3xl bg-brand-500 px-6 py-3 text-sm font-semibold text-white transition hover:bg-brand-600"
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                >
                  {isUploading ? 'Загружаем...' : 'Загрузить'}
                </motion.button>
              </div>
              {status && <p className="mt-5 text-sm text-slate-300">{status}</p>}
            </motion.div>
          </motion.div>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {uploadLimits.map((item, idx) => (
              <motion.div
                key={item.label}
                className="rounded-3xl border border-slate-800 bg-slate-950/90 p-5"
                whileHover={{ scale: 1.05, y: -5 }}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: idx * 0.05 }}
              >
                <p className="text-sm text-slate-400">{item.label}</p>
                <p className="mt-3 text-xl font-semibold text-white">{item.value}</p>
              </motion.div>
            ))}
          </div>
        </section>
      </div>
    </PageTransition>
  );
};

export default UploadPage;
