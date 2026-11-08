import React, { useState } from 'react';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import { ToastProvider } from './context/ToastContext';
import { Header } from './components/Header';
import { NavTab, Sidebar, tabsForRole } from './components/Sidebar';
import { AdminPage } from './pages/AdminPage';
import { ClientsPage } from './pages/ClientsPage';
import { LoginPage } from './pages/LoginPage';
import { LoyaltyPage } from './pages/LoyaltyPage';
import { MigrationPage } from './pages/MigrationPage';
import { OverviewPage } from './pages/OverviewPage';
import { SegmentationPage } from './pages/SegmentationPage';

const Workspace: React.FC = () => {
  const { user } = useAuth();
  const tabs = tabsForRole(user!.role);
  const [active, setActive] = useState<NavTab>(tabs[0].id);
  const [ruleDraftCluster, setRuleDraftCluster] = useState<number | null | undefined>(undefined);
  const [dataVersion, setDataVersion] = useState(0);

  const openRuleDraft = (clusterId: number | null) => {
    setRuleDraftCluster(clusterId);
    setActive('loyalty');
  };

  return (
    <div className="min-h-screen bg-[var(--bg-app)] text-[var(--text-main)] flex p-3.5 md:p-5 gap-4 md:gap-5 font-body">
      <Sidebar tabs={tabs} activeTab={active} onTabChange={setActive} />
      <div className="flex-1 flex flex-col min-w-0 h-[calc(100vh-2.5rem)] overflow-y-auto pr-1">
        <Header activeTab={active} onDataChanged={() => setDataVersion((v) => v + 1)} />
        <main className="flex-1 pb-8 w-full" key={`${active}-${dataVersion}`}>
          {active === 'overview' && <OverviewPage />}
          {active === 'admin' && <AdminPage />}
          {active === 'clients' && <ClientsPage onOpenSegmentation={() => setActive('segmentation')} />}
          {active === 'segmentation' && <SegmentationPage onCreateRule={openRuleDraft} />}
          {active === 'loyalty' && (
            <LoyaltyPage draftClusterId={ruleDraftCluster} onDraftConsumed={() => setRuleDraftCluster(undefined)}
              onOpenSegmentation={() => setActive('segmentation')} />
          )}
          {active === 'migration' && (
            <MigrationPage onCreateRule={openRuleDraft} onOpenSegmentation={() => setActive('segmentation')}
              onOpenLoyalty={() => setActive('loyalty')} />
          )}
        </main>
      </div>
    </div>
  );
};

const Root: React.FC = () => {
  const { isAuthenticated } = useAuth();
  return isAuthenticated ? <Workspace /> : <LoginPage />;
};

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <ToastProvider>
          <Root />
        </ToastProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}
