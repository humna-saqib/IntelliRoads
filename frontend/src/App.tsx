import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { TrafficProvider } from './context/TrafficContext';
import Sidebar from './components/layout/Sidebar';
import Header from './components/layout/Header';
import DashboardPage from './pages/DashboardPage';
import MapPage from './pages/MapPage';
import AnalyticsPage from './pages/AnalyticsPage';

export default function App() {
  return (
    <TrafficProvider>
      <Router>
        <div className="flex h-screen bg-[#0a0f1d] text-slate-100 overflow-hidden font-sans">
          {/* Sidebar Navigation */}
          <Sidebar />

          {/* Main Panel */}
          <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
            {/* Header / Control Bar */}
            <Header />

            {/* Scrollable Page Body */}
            <main className="flex-1 overflow-y-auto p-6 bg-[#0a0f1d] relative">
              {/* background ambient glow blobs */}
              <div className="absolute top-[-10%] left-[-10%] w-[50%] aspect-square rounded-full bg-purple-900/10 blur-[120px] pointer-events-none" />
              <div className="absolute bottom-[-10%] right-[-10%] w-[55%] aspect-square rounded-full bg-blue-900/10 blur-[130px] pointer-events-none" />

              <div className="max-w-7xl mx-auto relative z-10">
                <Routes>
                  <Route path="/" element={<DashboardPage />} />
                  <Route path="/map" element={<MapPage />} />
                  <Route path="/analytics" element={<AnalyticsPage />} />
                </Routes>
              </div>
            </main>
          </div>
        </div>
      </Router>
    </TrafficProvider>
  );
}
