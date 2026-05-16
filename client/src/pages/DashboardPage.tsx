import LoadingIndicator from '../components/LoadingIndicator';
import PageTransition from '../components/PageTransition';
import { motion } from 'framer-motion';

const stats = [
  { label: 'Проекты', value: '9' },
  { label: 'Загружено изображений', value: '1 324' },
  { label: 'Активных моделей', value: '3' },
  { label: 'Осталось кадров', value: '120' }
];

const DashboardPage = () => (
  <PageTransition>
    <div className="mx-auto max-w-[1400px]">
      <section className="space-y-6">
      <motion.div 
        className="rounded-[2rem] border border-slate-800 bg-slate-900/80 p-6"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
      >
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-3xl font-semibold text-white">Панель аннотатора</h1>
            <p className="text-slate-400">Обзор проектов, очередей и текущего тарифа.</p>
          </div>
          <LoadingIndicator label="Синхронизация очередей" />
        </div>
        <div className="mt-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {stats.map((item, idx) => (
            <motion.div
              key={item.label}
              className="rounded-[1.75rem] border border-slate-800 bg-slate-950/90 p-5"
              whileHover={{ scale: 1.05, y: -5 }}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 + idx * 0.05 }}
            >
              <p className="text-sm uppercase tracking-[0.2em] text-slate-500">{item.label}</p>
              <p className="mt-3 text-3xl font-semibold text-white">{item.value}</p>
            </motion.div>
          ))}
        </div>
      </motion.div>
      <div className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
        <motion.div 
          className="rounded-[2rem] border border-slate-800 bg-slate-900/80 p-6"
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.2 }}
        >
          <h2 className="text-xl font-semibold text-white">Последние задачи</h2>
          <div className="mt-5 space-y-4">
            {['Обработка 3 изображений', 'Сравнение модели SAM2', 'Загрузка нового датасета'].map((task, idx) => (
              <motion.div
                key={task}
                className="rounded-3xl border border-slate-800 bg-slate-950/90 p-4"
                whileHover={{ scale: 1.02, x: 5 }}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.3 + idx * 0.1 }}
              >
                <div className="flex items-center justify-between text-sm text-slate-400">
                  <span>{task}</span>
                  <span className="text-brand-400">В процессе</span>
                </div>
                <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-800">
                  <motion.div
                    className="h-full bg-gradient-to-r from-brand-500 to-brand-400"
                    style={{ width: '75%' }}
                    initial={{ width: 0 }}
                    animate={{ width: '75%' }}
                    transition={{ delay: 0.5 + idx * 0.1, duration: 0.8 }}
                  />
                </div>
              </motion.div>
            ))}
          </div>
        </motion.div>
        <motion.div 
          className="rounded-[2rem] border border-slate-800 bg-slate-900/80 p-6"
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.2 }}
        >
          <h2 className="text-xl font-semibold text-white">Лимиты подписки</h2>
          <div className="mt-5 space-y-4">
            {[
              { label: 'Форматы', value: 'JPG / PNG бесплатно, TIFF — по подписке' },
              { label: 'Параллельные задачи', value: 'до 4' }
            ].map((item, idx) => (
              <motion.div
                key={item.label}
                className="rounded-3xl border border-slate-800 bg-slate-950/90 p-4"
                whileHover={{ scale: 1.02, x: 5 }}
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.3 + idx * 0.1 }}
              >
                <div className="flex items-center justify-between text-sm text-slate-400">{item.label}</div>
                <div className="mt-3 text-lg font-semibold text-white">{item.value}</div>
              </motion.div>
            ))}
          </div>
        </motion.div>
      </div>
    </section>
  </div>
  </PageTransition>
);

export default DashboardPage;
