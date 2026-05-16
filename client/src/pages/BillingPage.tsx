import { motion } from 'framer-motion';
import PageTransition from '../components/PageTransition';
import { BadgeCheck, CreditCard, Receipt, ShieldCheck, Sparkles, Zap } from 'lucide-react';

const plans = [
  {
    name: 'Free',
    price: '0 ₽',
    description: 'Для быстрого старта и тестовых проектов',
    features: ['JPG / PNG', '2 параллельные задачи', 'Базовая история операций'],
    accent: 'border-slate-800 bg-slate-950/90'
  },
  {
    name: 'Pro',
    price: '4 900 ₽ / мес',
    description: 'Для командной разметки и production-нагрузки',
    features: ['TIFF и расширенные форматы', '5 параллельных задач', 'Приоритетная очередь моделей'],
    accent: 'border-brand-500/40 bg-brand-500/10'
  },
  {
    name: 'Enterprise',
    price: 'По запросу',
    description: 'Для изолированных контуров и корпоративных SLA',
    features: ['Выделенные лимиты', 'Кастомные роли и аудит', 'Интеграция с локальными моделями'],
    accent: 'border-cyan-500/30 bg-cyan-500/10'
  }
];

const paymentHistory = [
  { id: 'INV-2026-021', date: '16 апреля 2026', amount: '4 900 ₽', status: 'Оплачен' },
  { id: 'INV-2026-020', date: '16 марта 2026', amount: '4 900 ₽', status: 'Оплачен' },
  { id: 'INV-2026-019', date: '16 февраля 2026', amount: '4 900 ₽', status: 'Оплачен' }
];

const limits = [
  { label: 'Остаток кадров', value: '120', hint: 'обновление 1 мая' },
  { label: 'Параллельные задачи', value: '4 / 5', hint: '1 слот свободен' },
  { label: 'Активные проекты', value: '9', hint: 'лимит не достигнут' }
];

const BillingPage = () => (
  <PageTransition>
    <div className="mx-auto max-w-[1400px]">
      <section className="space-y-6">
        <motion.div
          className="overflow-hidden rounded-[2rem] border border-slate-800 bg-gradient-to-r from-slate-900 via-slate-900 to-brand-500/10 p-6"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-2xl">
              <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-brand-500/20 bg-brand-500/10 px-3 py-1 text-xs uppercase tracking-[0.22em] text-brand-100">
                <Sparkles size={14} />
                Подписка и оплата
              </div>
              <h1 className="text-3xl font-semibold text-white">Управление тарифом SegLabel AI</h1>
              <p className="mt-3 text-slate-300">
                Экран подписки с активным тарифом, лимитами, историей платежей и вариантами апгрейда.
              </p>
            </div>
            <div className="rounded-[1.75rem] border border-emerald-500/20 bg-emerald-500/10 px-5 py-4 text-sm text-emerald-100">
              <div className="flex items-center gap-2 font-semibold">
                <BadgeCheck size={16} />
                Текущий план: Pro
              </div>
              <div className="mt-1 text-emerald-200/80">Автопродление включено, следующее списание 16 мая 2026</div>
            </div>
          </div>
        </motion.div>

        <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
          <motion.div
            className="space-y-6"
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
          >
            <div className="grid gap-4 md:grid-cols-3">
              {limits.map((item, idx) => (
                <motion.div
                  key={item.label}
                  className="rounded-[1.75rem] border border-slate-800 bg-slate-900/80 p-5"
                  whileHover={{ scale: 1.02, y: -4 }}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: idx * 0.08 }}
                >
                  <div className="text-sm uppercase tracking-[0.18em] text-slate-500">{item.label}</div>
                  <div className="mt-3 text-3xl font-semibold text-white">{item.value}</div>
                  <div className="mt-2 text-sm text-slate-400">{item.hint}</div>
                </motion.div>
              ))}
            </div>

            <div className="rounded-[2rem] border border-slate-800 bg-slate-900/80 p-6">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <h2 className="text-xl font-semibold text-white">Способы оплаты</h2>
                  <p className="mt-1 text-slate-400">Подключенные реквизиты и параметры автопродления.</p>
                </div>
                <button className="inline-flex items-center justify-center gap-2 rounded-3xl bg-brand-500 px-5 py-3 text-sm font-semibold text-white transition hover:bg-brand-700">
                  <CreditCard size={16} />
                  Добавить карту
                </button>
              </div>

              <div className="mt-5 grid gap-4 md:grid-cols-2">
                <div className="rounded-[1.75rem] border border-slate-800 bg-slate-950/90 p-5">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-sm text-slate-400">Основная карта</div>
                      <div className="mt-2 text-lg font-semibold text-white">Visa •••• 4581</div>
                    </div>
                    <div className="rounded-full bg-emerald-500/15 px-3 py-1 text-xs font-semibold text-emerald-300">
                      По умолчанию
                    </div>
                  </div>
                  <div className="mt-4 flex items-center gap-2 text-sm text-slate-400">
                    <ShieldCheck size={16} />
                    3-D Secure и автоматическое продление активны
                  </div>
                </div>

                <div className="rounded-[1.75rem] border border-slate-800 bg-slate-950/90 p-5">
                  <div className="text-sm text-slate-400">Платёжный профиль</div>
                  <div className="mt-2 text-lg font-semibold text-white">ООО «AI-CV»</div>
                  <div className="mt-4 space-y-2 text-sm text-slate-400">
                    <div>ИНН: 7700000000</div>
                    <div>Email для счетов: billing@aicv.example</div>
                    <div>Закрывающие документы: ежемесячно</div>
                  </div>
                </div>
              </div>
            </div>

            <div className="rounded-[2rem] border border-slate-800 bg-slate-900/80 p-6">
              <div className="flex items-center gap-2">
                <Receipt size={18} className="text-brand-300" />
                <h2 className="text-xl font-semibold text-white">История платежей</h2>
              </div>
              <div className="mt-5 space-y-3">
                {paymentHistory.map((invoice, idx) => (
                  <motion.div
                    key={invoice.id}
                    className="flex flex-col gap-3 rounded-[1.5rem] border border-slate-800 bg-slate-950/90 px-4 py-4 sm:flex-row sm:items-center sm:justify-between"
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: idx * 0.08 }}
                  >
                    <div>
                      <div className="text-sm text-slate-400">{invoice.id}</div>
                      <div className="mt-1 font-semibold text-white">{invoice.date}</div>
                    </div>
                    <div className="text-sm text-slate-400">{invoice.amount}</div>
                    <div className="rounded-full bg-emerald-500/15 px-3 py-1 text-xs font-semibold text-emerald-300">
                      {invoice.status}
                    </div>
                  </motion.div>
                ))}
              </div>
            </div>
          </motion.div>

          <motion.div
            className="space-y-6"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
          >
            <div className="rounded-[2rem] border border-slate-800 bg-slate-900/80 p-6">
              <div className="flex items-center gap-2">
                <Zap size={18} className="text-brand-300" />
                <h2 className="text-xl font-semibold text-white">Апгрейд тарифа</h2>
              </div>
              <div className="mt-5 space-y-4">
                {plans.map((plan, idx) => (
                  <motion.div
                    key={plan.name}
                    className={`rounded-[1.75rem] border p-5 ${plan.accent}`}
                    whileHover={{ scale: 1.02, y: -4 }}
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: idx * 0.08 }}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <div className="text-lg font-semibold text-white">{plan.name}</div>
                        <div className="mt-1 text-sm text-slate-300">{plan.description}</div>
                      </div>
                      <div className="text-right text-sm text-slate-300">
                        <div className="text-xl font-semibold text-white">{plan.price}</div>
                      </div>
                    </div>
                    <div className="mt-4 space-y-2 text-sm text-slate-300">
                      {plan.features.map((feature) => (
                        <div key={feature} className="rounded-2xl border border-white/5 bg-slate-950/40 px-3 py-2">
                          {feature}
                        </div>
                      ))}
                    </div>
                  </motion.div>
                ))}
              </div>
            </div>

            <div className="rounded-[2rem] border border-slate-800 bg-slate-900/80 p-6">
              <h2 className="text-xl font-semibold text-white">Параметры подписки</h2>
              <div className="mt-5 space-y-3 text-sm text-slate-300">
                <div className="flex items-center justify-between rounded-3xl border border-slate-800 bg-slate-950/90 px-4 py-3">
                  <span>Автопродление</span>
                  <span className="text-emerald-300">Включено</span>
                </div>
                <div className="flex items-center justify-between rounded-3xl border border-slate-800 bg-slate-950/90 px-4 py-3">
                  <span>Порог уведомления о лимитах</span>
                  <span className="text-white">15%</span>
                </div>
                <div className="flex items-center justify-between rounded-3xl border border-slate-800 bg-slate-950/90 px-4 py-3">
                  <span>Доступ к TIFF</span>
                  <span className="text-white">Активен</span>
                </div>
              </div>
            </div>
          </motion.div>
        </div>
      </section>
    </div>
  </PageTransition>
);

export default BillingPage;
