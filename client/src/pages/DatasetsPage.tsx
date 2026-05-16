import { motion } from 'framer-motion';
import { FormEvent, useEffect, useState } from 'react';
import PageTransition from '../components/PageTransition';
import { api, type Project } from '../lib/api';

const formatDate = (value: string) =>
  new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));

const DatasetsPage = () => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectName, setProjectName] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  const loadProjects = async () => {
    setIsLoading(true);
    setError('');
    try {
      setProjects(await api.listProjects());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось загрузить проекты.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadProjects();
  }, []);

  const handleCreate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const name = projectName.trim();
    if (!name) {
      return;
    }

    try {
      const project = await api.createProject(name);
      setProjects((current) => [project, ...current]);
      setProjectName('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось создать проект.');
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
            <h1 className="text-3xl font-semibold text-white">Датасеты</h1>
            <p className="text-slate-400">Управляйте проектами, статусами загрузок и результатами.</p>
            <form onSubmit={handleCreate} className="mt-6 flex flex-col gap-3 sm:flex-row">
              <input
                value={projectName}
                onChange={(event) => setProjectName(event.target.value)}
                placeholder="Название проекта"
                className="min-w-0 flex-1 rounded-3xl border border-slate-800 bg-slate-950 px-4 py-3 text-slate-100 outline-none transition focus:border-brand-500"
              />
              <button className="rounded-3xl bg-brand-500 px-6 py-3 text-sm font-semibold text-white transition hover:bg-brand-600">
                Создать
              </button>
            </form>
            {error && <p className="mt-4 text-sm text-rose-300">{error}</p>}
          </motion.div>

          <div className="grid gap-4">
            {isLoading && <div className="rounded-[2rem] border border-slate-800 bg-slate-950/90 p-6 text-slate-400">Загружаем проекты...</div>}
            {!isLoading && projects.length === 0 && (
              <div className="rounded-[2rem] border border-slate-800 bg-slate-950/90 p-6 text-slate-400">Проектов пока нет.</div>
            )}
            {projects.map((project, idx) => (
              <motion.div
                key={project.id}
                className="rounded-[2rem] border border-slate-800 bg-slate-950/90 p-6"
                whileHover={{ scale: 1.02, y: -5 }}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: idx * 0.1 }}
              >
                <div className="flex flex-col gap-2 sm:flex-row sm:justify-between sm:items-center">
                  <div>
                    <h2 className="text-xl font-semibold text-white">{project.name}</h2>
                    <p className="text-sm text-slate-400">
                      Статус: <span className="text-brand-400">Готов к загрузке</span>
                    </p>
                  </div>
                  <div className="text-sm text-slate-400">Создан {formatDate(project.created_at)}</div>
                </div>
              </motion.div>
            ))}
          </div>
        </section>
      </div>
    </PageTransition>
  );
};

export default DatasetsPage;
