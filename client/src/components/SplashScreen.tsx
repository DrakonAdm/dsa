import { useEffect, useState } from 'react';

interface SplashScreenProps {
  onLoadComplete: () => void;
}

const SplashScreen = ({ onLoadComplete }: SplashScreenProps) => {
  const [isVisible, setIsVisible] = useState(true);

  useEffect(() => {
    const timer = setTimeout(() => {
      setIsVisible(false);
      setTimeout(onLoadComplete, 500); // Небольшая задержка для плавного исчезновения
    }, 3000);

    return () => clearTimeout(timer);
  }, [onLoadComplete]);

  if (!isVisible) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950 transition-opacity duration-500">
      <div className="relative flex items-center justify-center">
        {/* Центральное изображение */}
        <img
          src="/splash_screen.png"
          alt="Splash Screen"
          className="relative z-10 w-64 h-64 object-contain animate-fade-in"
        />
      </div>
    </div>
  );
};

export default SplashScreen;
