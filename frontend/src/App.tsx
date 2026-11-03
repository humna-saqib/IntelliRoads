import { useEffect, useState } from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { TrafficProvider } from './context/TrafficContext';
import Sidebar from './components/layout/Sidebar';
import Header from './components/layout/Header';
import DashboardPage from './pages/DashboardPage';
import MapPage from './pages/MapPage';
import AnalyticsPage from './pages/AnalyticsPage';
import ReportsPage from './pages/ReportsPage';
import AlertHistoryPage from './pages/AlertHistoryPage';
import SettingsPage from './pages/SettingsPage';
import LoginPage from './pages/LoginPage';

export default function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('intelliroads_token'));

  useEffect(() => {
    const handleUnauthorized = () => setToken(null);
    window.addEventListener('intelliroads:unauthorized', handleUnauthorized);
    return () => window.removeEventListener('intelliroads:unauthorized', handleUnauthorized);
  }, []);

  const handleLogout = () => {
    localStorage.removeItem('intelliroads_token');
    setToken(null);
  };

  if (!token) {
    return <LoginPage onLoginSuccess={(newToken) => setToken(newToken)} />;
  }

  return (
    <TrafficProvider>
      <Router>
        <div className="flex h-screen overflow-hidden bg-page text-ink">
          <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />

          <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
            <Header onMenuClick={() => setSidebarOpen(true)} onLogout={handleLogout} />

            <main className="flex-1 overflow-y-auto">
              <div className="mx-auto w-full max-w-[1200px] px-4 py-5 sm:px-6 sm:py-6">
                <Routes>
                  <Route path="/" element={<DashboardPage />} />
                  <Route path="/map" element={<MapPage />} />
                  <Route path="/analytics" element={<AnalyticsPage />} />
                  <Route path="/alerts" element={<AlertHistoryPage />} />
                  <Route path="/reports" element={<ReportsPage />} />
                  <Route path="/settings" element={<SettingsPage />} />
                </Routes>
              </div>
            </main>
          </div>
        </div>
      </Router>
    </TrafficProvider>
  );
}
