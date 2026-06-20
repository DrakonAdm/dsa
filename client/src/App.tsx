import { Route, Routes, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { AnimatePresence } from 'framer-motion';
import {
  AuthPage,
  WorkspacePage,
  DatasetsPage,
  ModelsPage,
  ProfilePage,
  UploadPage,
  AdminPage,
  BillingPage
} from './pages';
import { TopNav } from './components';
import SplashScreen from './components/SplashScreen';
import { api, type AuthPayload } from './lib/api';

const AUTH_REFRESH_INTERVAL_MS = 14 * 60 * 1000;

const App = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const [isAuthorized, setIsAuthorized] = useState(Boolean(api.tokenStorage.getAccess()));
  const [isCheckingSession, setIsCheckingSession] = useState(Boolean(api.tokenStorage.getAccess()));
  const [isSplashVisible, setIsSplashVisible] = useState(false);

  useEffect(() => {
    if (!api.tokenStorage.getAccess()) {
      return;
    }

    api
      .getMe()
      .then(() => setIsAuthorized(true))
      .catch(() => {
        api.tokenStorage.clear();
        setIsAuthorized(false);
      })
      .finally(() => setIsCheckingSession(false));
  }, []);

  const handleLogin = async (payload: AuthPayload) => {
    await api.login(payload);
    setIsAuthorized(true);
    setIsSplashVisible(true);
    navigate('/projects');
  };

  useEffect(() => {
    if (!isAuthorized) {
      return undefined;
    }

    const refreshIntervalId = window.setInterval(() => {
      api.refreshSession().catch(() => {
        api.tokenStorage.clear();
        setIsAuthorized(false);
        navigate('/auth');
      });
    }, AUTH_REFRESH_INTERVAL_MS);

    return () => window.clearInterval(refreshIntervalId);
  }, [isAuthorized, navigate]);

  if (isCheckingSession) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950 text-slate-300">
        Проверяем сессию...
      </div>
    );
  }

  if (isSplashVisible) {
    return <SplashScreen onLoadComplete={() => setIsSplashVisible(false)} />;
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-slate-950 text-slate-100">
      {isAuthorized && <TopNav />}
      <main
        className={
          location.pathname.startsWith('/workspace')
            ? 'min-h-0 flex-1 overflow-hidden'
            : 'app-scroll min-h-0 flex-1 overflow-x-hidden overflow-y-auto px-4 py-5 xl:px-12'
        }
      >
        <AnimatePresence mode="wait">
          <Routes location={location} key={location.pathname}>
            <Route path="/" element={<Navigate to={isAuthorized ? '/projects' : '/auth'} replace />} />
            <Route path="/auth" element={isAuthorized ? <Navigate to="/projects" replace /> : <AuthPage onLogin={handleLogin} />} />
            <Route path="/dashboard" element={<Navigate to={isAuthorized ? '/projects' : '/auth'} replace />} />
            <Route path="/projects" element={isAuthorized ? <DatasetsPage /> : <Navigate to="/auth" replace />} />
            <Route path="/models" element={isAuthorized ? <ModelsPage /> : <Navigate to="/auth" replace />} />
            <Route path="/upload" element={isAuthorized ? <UploadPage /> : <Navigate to="/auth" replace />} />
            <Route path="/workspace" element={isAuthorized ? <WorkspacePage /> : <Navigate to="/auth" replace />} />
            <Route path="/workspace/:projectId" element={isAuthorized ? <WorkspacePage /> : <Navigate to="/auth" replace />} />
            <Route path="/profile" element={isAuthorized ? <ProfilePage /> : <Navigate to="/auth" replace />} />
            <Route path="/billing" element={isAuthorized ? <BillingPage /> : <Navigate to="/auth" replace />} />
            <Route path="/admin" element={isAuthorized ? <AdminPage /> : <Navigate to="/auth" replace />} />
            <Route path="*" element={<div className="mt-20 text-center text-lg">Страница не найдена</div>} />
          </Routes>
        </AnimatePresence>
      </main>
    </div>
  );
};

export default App;
