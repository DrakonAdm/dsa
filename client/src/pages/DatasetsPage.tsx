import { motion } from 'framer-motion';
import { FormEvent, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, Search, Trash2, UserPlus, X } from 'lucide-react';
import PageTransition from '../components/PageTransition';
import { api, type Project, type ProjectMemberCandidate } from '../lib/api';

const formatDate = (value?: string) => {
  if (!value) {
    return 'только что';
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return 'только что';
  }

  return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'short' }).format(date);
};

const DatasetsPage = () => {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectName, setProjectName] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [deletingProjectId, setDeletingProjectId] = useState<Project['id'] | null>(null);
  const [projectPendingDelete, setProjectPendingDelete] = useState<Project | null>(null);
  const [projectPendingMember, setProjectPendingMember] = useState<Project | null>(null);
  const [memberQuery, setMemberQuery] = useState('');
  const [memberResults, setMemberResults] = useState<ProjectMemberCandidate[]>([]);
  const [memberStatus, setMemberStatus] = useState('');
  const [isSearchingMembers, setIsSearchingMembers] = useState(false);
  const [addingMemberProjectId, setAddingMemberProjectId] = useState<Project['id'] | null>(null);
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

  const handleDelete = async () => {
    if (!projectPendingDelete) {
      return;
    }

    setDeletingProjectId(projectPendingDelete.id);
    setError('');

    try {
      await api.deleteProject(projectPendingDelete.id);
      setProjects((current) => current.filter((item) => item.id !== projectPendingDelete.id));
      setProjectPendingDelete(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось удалить проект.');
    } finally {
      setDeletingProjectId(null);
    }
  };

  useEffect(() => {
    void loadProjects();
  }, []);

  useEffect(() => {
    const query = memberQuery.trim();

    if (!projectPendingMember || query.length < 2) {
      setMemberResults([]);
      setIsSearchingMembers(false);
      return undefined;
    }

    let isCancelled = false;
    setIsSearchingMembers(true);

    const timeoutId = window.setTimeout(() => {
      api
        .searchProjectUsers(query)
        .then((items) => {
          if (!isCancelled) {
            setMemberResults(items);
          }
        })
        .catch((err) => {
          if (!isCancelled) {
            setMemberStatus(err instanceof Error ? err.message : 'Не удалось найти пользователей.');
            setMemberResults([]);
          }
        })
        .finally(() => {
          if (!isCancelled) {
            setIsSearchingMembers(false);
          }
        });
    }, 250);

    return () => {
      isCancelled = true;
      window.clearTimeout(timeoutId);
    };
  }, [memberQuery, projectPendingMember]);

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

  const openMemberDialog = (project: Project) => {
    setProjectPendingMember(project);
    setMemberQuery('');
    setMemberResults([]);
    setMemberStatus('');
  };

  const closeMemberDialog = () => {
    if (addingMemberProjectId) {
      return;
    }

    setProjectPendingMember(null);
    setMemberQuery('');
    setMemberResults([]);
    setMemberStatus('');
  };

  const handleAddMember = async (value = memberQuery) => {
    const memberValue = value.trim();

    if (!projectPendingMember || !memberValue) {
      setMemberStatus('Введите login или email пользователя.');
      return;
    }

    setAddingMemberProjectId(projectPendingMember.id);
    setMemberStatus('');

    try {
      const result = await api.addProjectMember(projectPendingMember.id, memberValue);
      setMemberStatus(result.detail);
      setMemberQuery('');
      setMemberResults([]);
    } catch (err) {
      setMemberStatus(err instanceof Error ? err.message : 'Не удалось добавить участника.');
    } finally {
      setAddingMemberProjectId(null);
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
            <h1 className="text-3xl font-semibold text-white">Проекты</h1>
            <p className="text-slate-400">Создавайте проекты, управляйте списком и переходите к загрузке датасетов.</p>
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
                role="button"
                tabIndex={0}
                onClick={() => navigate(`/workspace/${project.id}`)}
                onKeyDown={(event) => {
                  if (event.target === event.currentTarget && (event.key === 'Enter' || event.key === ' ')) {
                    event.preventDefault();
                    navigate(`/workspace/${project.id}`);
                  }
                }}
                className="cursor-pointer rounded-[2rem] border border-slate-800 bg-slate-950/90 p-6 outline-none transition focus:border-brand-500/60"
                whileHover={{ scale: 1.02, y: -5 }}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: idx * 0.1 }}
              >
                <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <h2 className="text-xl font-semibold text-white">{project.name}</h2>
                    <p className="text-sm text-slate-400">
                      Статус: <span className="text-brand-400">Готов к загрузке</span>
                    </p>
                  </div>
                  <div className="flex flex-col gap-3 sm:items-end">
                    <div className="text-sm text-slate-400">Создан {formatDate(project.created_at)}</div>
                    <div className="flex flex-wrap justify-start gap-2 sm:justify-end">
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          openMemberDialog(project);
                        }}
                        className="inline-flex items-center justify-center gap-2 rounded-2xl border border-brand-500/25 bg-brand-500/10 px-4 py-2 text-sm font-semibold text-brand-100 transition hover:border-brand-400/50 hover:bg-brand-500/15"
                      >
                        <UserPlus size={15} />
                        Добавить участника
                      </button>
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          setProjectPendingDelete(project);
                        }}
                        disabled={deletingProjectId === project.id}
                        className="inline-flex items-center justify-center gap-2 rounded-2xl border border-rose-500/25 bg-rose-500/10 px-4 py-2 text-sm font-semibold text-rose-100 transition hover:border-rose-400/50 hover:bg-rose-500/15 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        <Trash2 size={15} />
                        {deletingProjectId === project.id ? 'Удаляем...' : 'Удалить'}
                      </button>
                    </div>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </section>
      </div>

      {projectPendingDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/75 px-4 backdrop-blur-sm">
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-project-title"
            className="w-full max-w-md rounded-[24px] border border-slate-700 bg-slate-900 p-5 shadow-2xl"
            initial={{ opacity: 0, scale: 0.96, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
          >
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="rounded-2xl bg-rose-500/12 p-3 text-rose-200">
                  <AlertTriangle size={20} />
                </div>
                <div>
                  <h2 id="delete-project-title" className="text-lg font-semibold text-white">
                    Удалить проект?
                  </h2>
                  <p className="mt-1 text-sm text-slate-400">Это действие нельзя отменить.</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setProjectPendingDelete(null)}
                className="rounded-xl border border-slate-700 bg-slate-950 p-2 text-slate-400 transition hover:text-white"
                aria-label="Закрыть"
              >
                <X size={16} />
              </button>
            </div>

            <div className="mt-5 rounded-2xl border border-slate-800 bg-slate-950 px-4 py-3 text-sm text-slate-200">
              {projectPendingDelete.name}
            </div>

            <div className="mt-5 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
              <button
                type="button"
                onClick={() => setProjectPendingDelete(null)}
                disabled={deletingProjectId === projectPendingDelete.id}
                className="rounded-2xl border border-slate-700 px-5 py-2.5 text-sm font-semibold text-slate-200 transition hover:border-slate-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                Отмена
              </button>
              <button
                type="button"
                onClick={handleDelete}
                disabled={deletingProjectId === projectPendingDelete.id}
                className="inline-flex items-center justify-center gap-2 rounded-2xl bg-rose-500 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-rose-400 disabled:cursor-not-allowed disabled:bg-rose-500/50"
              >
                <Trash2 size={15} />
                {deletingProjectId === projectPendingDelete.id ? 'Удаляем...' : 'Удалить'}
              </button>
            </div>
          </motion.div>
        </div>
      )}

      {projectPendingMember && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/75 px-4 backdrop-blur-sm">
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby="member-project-title"
            className="w-full max-w-lg rounded-[24px] border border-slate-700 bg-slate-900 p-5 shadow-2xl"
            initial={{ opacity: 0, scale: 0.96, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
          >
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="rounded-2xl bg-brand-500/12 p-3 text-brand-100">
                  <UserPlus size={20} />
                </div>
                <div>
                  <h2 id="member-project-title" className="text-lg font-semibold text-white">
                    Добавить участника
                  </h2>
                  <p className="mt-1 text-sm text-slate-400">{projectPendingMember.name}</p>
                </div>
              </div>
              <button
                type="button"
                onClick={closeMemberDialog}
                disabled={Boolean(addingMemberProjectId)}
                className="rounded-xl border border-slate-700 bg-slate-950 p-2 text-slate-400 transition hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                aria-label="Закрыть"
              >
                <X size={16} />
              </button>
            </div>

            <form
              onSubmit={(event) => {
                event.preventDefault();
                void handleAddMember();
              }}
              className="mt-5"
            >
              <label className="text-sm font-medium text-slate-300" htmlFor="project-member-query">
                Login или email
              </label>
              <div className="mt-2 flex gap-2">
                <div className="relative min-w-0 flex-1">
                  <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" size={16} />
                  <input
                    id="project-member-query"
                    value={memberQuery}
                    onChange={(event) => {
                      setMemberQuery(event.target.value);
                      setMemberStatus('');
                    }}
                    placeholder="ivan или ivan@example.com"
                    className="w-full rounded-2xl border border-slate-800 bg-slate-950 py-3 pl-10 pr-4 text-slate-100 outline-none transition focus:border-brand-500"
                  />
                </div>
                <button
                  type="submit"
                  disabled={Boolean(addingMemberProjectId) || !memberQuery.trim()}
                  className="inline-flex items-center justify-center gap-2 rounded-2xl bg-brand-500 px-5 py-3 text-sm font-semibold text-white transition hover:bg-brand-600 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
                >
                  <UserPlus size={15} />
                  {addingMemberProjectId ? 'Добавляем...' : 'Добавить'}
                </button>
              </div>
            </form>

            <div className="mt-4 min-h-[120px] rounded-2xl border border-slate-800 bg-slate-950/80 p-3">
              {isSearchingMembers && <div className="px-2 py-3 text-sm text-slate-400">Ищем пользователей...</div>}
              {!isSearchingMembers && memberQuery.trim().length < 2 && (
                <div className="px-2 py-3 text-sm text-slate-500">Введите минимум 2 символа.</div>
              )}
              {!isSearchingMembers && memberQuery.trim().length >= 2 && memberResults.length === 0 && (
                <div className="px-2 py-3 text-sm text-slate-500">Пользователи не найдены.</div>
              )}
              {!isSearchingMembers && memberResults.length > 0 && (
                <div className="space-y-2">
                  {memberResults.map((user) => (
                    <button
                      key={`${user.email}-${user.login}`}
                      type="button"
                      onClick={() => void handleAddMember(user.login || user.email)}
                      disabled={Boolean(addingMemberProjectId)}
                      className="flex w-full items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-900 px-3 py-2 text-left transition hover:border-brand-500/50 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-semibold text-slate-100">{user.login}</span>
                        <span className="block truncate text-xs text-slate-500">{user.email}</span>
                      </span>
                      {user.name_company && <span className="shrink-0 text-xs text-slate-500">{user.name_company}</span>}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {memberStatus && <p className="mt-3 text-sm text-slate-300">{memberStatus}</p>}
          </motion.div>
        </div>
      )}
    </PageTransition>
  );
};

export default DatasetsPage;
