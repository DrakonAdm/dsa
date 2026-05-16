const LoadingIndicator = ({ label = 'Загрузка' }: { label?: string }) => (
  <div className="flex items-center gap-3 rounded-3xl bg-slate-900/90 px-4 py-3 text-slate-200 shadow-lg shadow-slate-950/40">
    <div className="h-3 w-3 animate-pulse rounded-full bg-brand-500" />
    <span>{label}...</span>
  </div>
);

export default LoadingIndicator;
