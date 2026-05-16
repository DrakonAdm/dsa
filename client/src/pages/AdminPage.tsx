import Sidebar from '../components/Sidebar';
import { motion } from 'framer-motion';
import PageTransition from '../components/PageTransition';
import { Activity, BadgeCheck, Clock3, Shield, Users } from 'lucide-react';
import { useState } from 'react';

const services = [
  { name: 'SAM2', port: 8001, status: 'online' },
  { name: 'YOLO-World', port: 8002, status: 'online' },
  { name: 'GroundingDino', port: 8003, status: 'idle' }
];

const queueMetrics = [
  { label: 'Активных пользователей', value: '24', icon: Users },
  { label: 'Задач в очереди', value: '13', icon: Clock3 },
  { label: 'Успешных прогонов', value: '98.7%', icon: BadgeCheck },
  { label: 'Политик доступа', value: '6', icon: Shield }
];

const moderationQueue = [
  { user: 'Анна Морозова', role: 'Анотатор', project: 'Городской трафик', status: 'Ожидает доступа' },
  { user: 'Илья Соколов', role: 'ML Engineer', project: 'SAM2 Validation', status: 'Требует ревью лимитов' },
  { user: 'Екатерина Белова', role: 'Администратор', project: 'Внутренний контур', status: 'Назначение роли' }
];

const AdminPage = () => {
  const [selectedTool, setSelectedTool] = useState<string | null>(null);

  return (
    <PageTransition>
      <div className="mx-auto grid max-w-[1400px] gap-6 xl:grid-cols-[300px_minmax(0,1fr)]">
        <Sidebar selectedTool={selectedTool} onToolSelect={setSelectedTool} />
      <section className="space-y-6">
        <motion.div
          className="rounded-[2rem] border border-slate-800 bg-slate-900/80 p-6"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <h1 className="text-3xl font-semibold text-white">Администрирование</h1>
              <p className="mt-2 text-slate-400">Права доступа, очереди задач, модели, лимиты подписок и состояние сервисов.</p>
            </div>
            <div className="rounded-[1.5rem] border border-brand-500/20 bg-brand-500/10 px-4 py-3 text-sm text-brand-100">
              Обновление статусов в реальном времени через очередь задач WS
            </div>
          </div>
        </motion.div>

        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {queueMetrics.map((metric, idx) => {
            const Icon = metric.icon;
            return (
              <motion.div
                key={metric.label}
                className="rounded-[1.75rem] border border-slate-800 bg-slate-900/80 p-5"
                whileHover={{ scale: 1.03, y: -4 }}
                initial={{ opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: idx * 0.06 }}
              >
                <div className="flex items-center gap-3 text-slate-400">
                  <div className="rounded-2xl border border-slate-800 bg-slate-950/90 p-2">
                    <Icon size={16} />
                  </div>
                  <span className="text-sm uppercase tracking-[0.16em]">{metric.label}</span>
                </div>
                <div className="mt-4 text-3xl font-semibold text-white">{metric.value}</div>
              </motion.div>
            );
          })}
        </div>

        <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
          <motion.div
            className="rounded-[2rem] border border-slate-800 bg-slate-950/90 p-6"
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
          >
            <div className="flex items-center gap-2">
              <Activity size={18} className="text-brand-300" />
              <h2 className="text-xl font-semibold text-white">Мониторинг сервисов</h2>
            </div>
            <div className="mt-5 space-y-4">
              {services.map((service, idx) => (
                <motion.div
                  key={service.name}
                  className="rounded-3xl border border-slate-800 bg-slate-900/80 p-4"
                  whileHover={{ scale: 1.02, x: 5 }}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: idx * 0.1 }}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <div className="text-lg font-semibold text-white">{service.name}</div>
                      <div className="text-sm text-slate-400">Порт {service.port}</div>
                    </div>
                    <motion.span
                      className={`rounded-full px-3 py-1 text-xs font-semibold ${
                        service.status === 'online' ? 'bg-emerald-500/15 text-emerald-300' : 'bg-slate-800 text-slate-400'
                      }`}
                      animate={{
                        boxShadow: service.status === 'online'
                          ? ['0 0 0 0 rgba(16, 185, 129, 0.4)', '0 0 0 10px rgba(16, 185, 129, 0)']
                          : 'none'
                      }}
                      transition={{ duration: 2, repeat: Infinity }}
                    >
                      {service.status}
                    </motion.span>
                  </div>
                  <div className="mt-4 grid gap-3 sm:grid-cols-2">
                    <div className="rounded-2xl border border-slate-800 bg-slate-950/90 px-3 py-3 text-sm text-slate-400">
                      Средний отклик: <span className="text-white">148 мс</span>
                    </div>
                    <div className="rounded-2xl border border-slate-800 bg-slate-950/90 px-3 py-3 text-sm text-slate-400">
                      Очередь задач: <span className="text-white">{idx + 2}</span>
                    </div>
                  </div>
                </motion.div>
              ))}
            </div>
          </motion.div>

          <motion.div
            className="space-y-6"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
          >
            <div className="rounded-[2rem] border border-slate-800 bg-slate-950/90 p-6">
              <h2 className="text-xl font-semibold text-white">Очередь согласования</h2>
              <div className="mt-5 space-y-3">
                {moderationQueue.map((entry) => (
                  <div key={entry.user} className="rounded-3xl border border-slate-800 bg-slate-900/80 p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-base font-semibold text-white">{entry.user}</div>
                        <div className="mt-1 text-sm text-slate-400">{entry.role} • {entry.project}</div>
                      </div>
                      <div className="rounded-full bg-amber-500/15 px-3 py-1 text-xs font-semibold text-amber-300">
                        {entry.status}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-[2rem] border border-slate-800 bg-slate-950/90 p-6">
              <h2 className="text-xl font-semibold text-white">Тарифы и права</h2>
              <div className="mt-5 space-y-4 text-slate-300">
                {[
                  { name: 'Free', desc: 'JPG / PNG, 2 параллельных задачи, базовый аудит' },
                  { name: 'Pro', desc: 'TIFF включен, 5 параллельных задач, приоритетная очередь' },
                  { name: 'Enterprise', desc: 'SSO, расширенные роли, журнал действий и выделенные лимиты' }
                ].map((plan, idx) => (
                  <motion.div
                    key={plan.name}
                    className="rounded-3xl border border-slate-800 bg-slate-900/80 p-4"
                    whileHover={{ scale: 1.02, x: 5 }}
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: idx * 0.1 }}
                  >
                    <div className="text-sm text-slate-400">{plan.name}</div>
                    <div className="mt-2 text-lg font-semibold text-white">{plan.desc}</div>
                  </motion.div>
                ))}
              </div>
            </div>
          </motion.div>
        </div>
      </section>
      </div>
    </PageTransition>
  );
};

export default AdminPage;
