import { motion } from 'framer-motion';
import { useEffect, useState } from 'react';
import PageTransition from '../components/PageTransition';
import { api, type UserBase, type UserDefinition } from '../lib/api';

const ProfilePage = () => {
  const [user, setUser] = useState<UserBase | null>(null);
  const [definition, setDefinition] = useState<UserDefinition | null>(null);
  const [status, setStatus] = useState('');

  useEffect(() => {
    Promise.all([api.getMe(), api.getDefinitionMe()])
      .then(([userData, definitionData]) => {
        setUser(userData);
        setDefinition(definitionData);
      })
      .catch((err) => setStatus(err instanceof Error ? err.message : 'Не удалось загрузить профиль.'));
  }, []);

  return (
    <PageTransition>
      <div className="mx-auto max-w-[1400px]">
        <section className="space-y-6">
          <motion.div
            className="rounded-[2rem] border border-slate-800 bg-slate-900/80 p-6"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <h1 className="text-3xl font-semibold text-white">Личный кабинет</h1>
            <p className="text-slate-400">Профиль, история задач и лимиты подписки.</p>
            {status && <p className="mt-4 text-sm text-rose-300">{status}</p>}
          </motion.div>
          <div className="grid gap-6 xl:grid-cols-[1fr_0.9fr]">
            <motion.div
              className="rounded-[2rem] border border-slate-800 bg-slate-950/90 p-6"
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
            >
              <h2 className="text-xl font-semibold text-white">Профиль пользователя</h2>
              <div className="mt-6 space-y-4 text-slate-300">
                <motion.div className="grid grid-cols-2 gap-4 rounded-3xl border border-slate-800 bg-slate-900/80 p-4" whileHover={{ scale: 1.02 }}>
                  <span className="text-slate-400">Логин</span>
                  <span>{user?.login ?? '...'}</span>
                  <span className="text-slate-400">Организация</span>
                  <span>{definition?.name_company ?? 'Не указана'}</span>
                  <span className="text-slate-400">Описание</span>
                  <span>{definition?.definition ?? 'Не указано'}</span>
                  <span className="text-slate-400">Подписка</span>
                  <span className="text-brand-400">Base</span>
                </motion.div>
              </div>
            </motion.div>
            <motion.div className="rounded-[2rem] border border-slate-800 bg-slate-950/90 p-6" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }}>
              <h2 className="text-xl font-semibold text-white">История задач</h2>
              <div className="mt-5 space-y-4">
                {['Сессия авторизации активна', 'Проекты синхронизируются с backend', 'Загрузки отправляются через API'].map((item, idx) => (
                  <motion.div
                    key={item}
                    className="rounded-3xl border border-slate-800 bg-slate-900/80 p-4 text-slate-200"
                    whileHover={{ scale: 1.02, x: 5 }}
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: idx * 0.1 }}
                  >
                    {item}
                  </motion.div>
                ))}
              </div>
            </motion.div>
          </div>
        </section>
      </div>
    </PageTransition>
  );
};

export default ProfilePage;
