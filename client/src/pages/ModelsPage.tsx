import { ArrowUpRight, HardDrive, Server } from 'lucide-react';
import { motion } from 'framer-motion';
import { useEffect, useState } from 'react';
import PageTransition from '../components/PageTransition';
import { api, type ModelConfig, type Project } from '../lib/api';

const modelTypeLabel: Record<string, string> = {
  segmentation: 'Сегментация',
  detection: 'Детекция',
  sahi_detection: 'SAHI детекция',
  sahi_segmentation: 'SAHI сегментация'
};

const ModelsPage = () => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState('');
  const [models, setModels] = useState<ModelConfig[]>([]);
  const [status, setStatus] = useState('');

  useEffect(() => {
    api
      .listProjects()
      .then((items) => {
        setProjects(items);
        setSelectedProjectId(items[0]?.id ?? '');
      })
      .catch((err) => setStatus(err instanceof Error ? err.message : 'Не удалось загрузить проекты.'));
  }, []);

  useEffect(() => {
    if (!selectedProjectId) {
      setModels([]);
      return;
    }

    api
      .getProjectModels(selectedProjectId)
      .then(setModels)
      .catch((err) => setStatus(err instanceof Error ? err.message : 'Не удалось загрузить модели.'));
  }, [selectedProjectId]);

  return (
    <PageTransition>
      <div className="mx-auto max-w-[1400px]">
        <section className="space-y-6">
          <motion.div
            className="rounded-[2rem] border border-slate-800 bg-slate-900/80 p-6"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
              <div>
                <h1 className="text-3xl font-semibold text-white">Управление моделями</h1>
                <p className="text-slate-400">Модели, доступные для выбранного проекта.</p>
              </div>
              <select
                value={selectedProjectId}
                onChange={(event) => setSelectedProjectId(event.target.value)}
                className="rounded-3xl border border-slate-800 bg-slate-950 px-4 py-3 text-slate-100 outline-none transition focus:border-brand-500"
              >
                <option value="">Проект не выбран</option>
                {projects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                  </option>
                ))}
              </select>
              <motion.button
                type="button"
                onClick={() => selectedProjectId && api.getProjectModels(selectedProjectId).then(setModels)}
                className="inline-flex items-center gap-2 rounded-3xl bg-brand-500 px-5 py-3 text-sm font-semibold text-white transition hover:bg-brand-600"
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
              >
                <ArrowUpRight size={16} /> Проверить Health
              </motion.button>
            </div>
            {status && <p className="mt-4 text-sm text-rose-300">{status}</p>}
          </motion.div>
          <div className="grid gap-4 lg:grid-cols-2">
            {models.length === 0 && (
              <div className="rounded-[2rem] border border-slate-800 bg-slate-950/90 p-6 text-slate-400">Нет данных по моделям.</div>
            )}
            {models.map((item, idx) => (
              <motion.div
                key={`${item.id}-${item.name}`}
                className="rounded-[2rem] border border-slate-800 bg-slate-950/90 p-6"
                whileHover={{ scale: 1.03, y: -5 }}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: idx * 0.1 }}
              >
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <h2 className="text-xl font-semibold text-white">{item.name}</h2>
                    <p className="text-sm text-slate-400">{modelTypeLabel[item.type] ?? item.type}</p>
                  </div>
                  <motion.span
                    className="rounded-full bg-emerald-500/15 px-3 py-1 text-xs font-semibold text-emerald-300"
                    animate={{ boxShadow: ['0 0 0 0 rgba(16, 185, 129, 0.4)', '0 0 0 10px rgba(16, 185, 129, 0)'] }}
                    transition={{ duration: 2, repeat: Infinity }}
                  >
                    available
                  </motion.span>
                </div>
                <div className="mt-5 grid gap-3 sm:grid-cols-2">
                  <motion.div className="rounded-3xl border border-slate-800 bg-slate-900/80 p-4" whileHover={{ scale: 1.05 }}>
                    <div className="flex items-center gap-2 text-slate-400">
                      <Server size={16} />
                      <span>ID</span>
                    </div>
                    <div className="mt-2 text-lg font-semibold text-white">{item.id}</div>
                  </motion.div>
                  <motion.div className="rounded-3xl border border-slate-800 bg-slate-900/80 p-4" whileHover={{ scale: 1.05 }}>
                    <div className="flex items-center gap-2 text-slate-400">
                      <HardDrive size={16} />
                      <span>Ресурсы</span>
                    </div>
                    <div className="mt-2 text-lg font-semibold text-white">GPU / CPU</div>
                  </motion.div>
                </div>
              </motion.div>
            ))}
          </div>
        </section>
      </div>
    </PageTransition>
  );
};

export default ModelsPage;
