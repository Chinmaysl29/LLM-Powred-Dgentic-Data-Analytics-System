import { lazy, Suspense } from 'react';
import { Navigate, Outlet, Routes, Route, useLocation } from 'react-router-dom';
import { useAuth } from './context/AuthContext';
import AppErrorBoundary from './components/AppErrorBoundary';
const LegalPage = lazy(() => import('./pages/LegalPage'));

const AuthLayout = lazy(() => import('./layouts/AuthLayout'));
const AppLayout = lazy(() => import('./layouts/AppLayout'));

const LoginPage = lazy(() => import('./pages/auth/LoginPage'));
const SignupPage = lazy(() => import('./pages/auth/SignupPage'));
const ForgotPasswordPage = lazy(() => import('./pages/auth/ForgotPasswordPage'));

const DashboardPage = lazy(() => import('./pages/app/DashboardPage'));
const DatasetsPage = lazy(() => import('./pages/app/DatasetsPage'));
const DatasetDetailPage = lazy(() => import('./pages/app/DatasetDetailPage'));
const DatasetUploadPage = lazy(() => import('./pages/app/DatasetUploadPage'));
const ConnectionsPage = lazy(() => import('./pages/app/ConnectionsPage'));
const DataWarehousePage = lazy(() => import('./pages/app/DataWarehousePage'));
const ProfilePage = lazy(() => import('./pages/app/ProfilePage'));
const AnalysisPage = lazy(() => import('./pages/app/AnalysisPage'));
const VisualizationsPage = lazy(() => import('./pages/app/VisualizationsPage'));
const InsightsPage = lazy(() => import('./pages/app/InsightsPage'));
const ReportsPage = lazy(() => import('./pages/app/ReportsPage'));
const CreateReportPage = lazy(() => import('./pages/app/CreateReportPage'));
const ReportDetailPage = lazy(() => import('./pages/app/ReportDetailPage'));
const ReportBuilderPage = lazy(() => import('./pages/app/ReportBuilderPage'));
const SettingsPage = lazy(() => import('./pages/app/SettingsPage'));
const ForecastingWorkbenchPage = lazy(() => import('./pages/app/ForecastingWorkbenchPage'));
const AIMemoryExplorerPage = lazy(() => import('./pages/app/AIMemoryExplorerPage'));
const DashboardStudioPage = lazy(() => import('./pages/app/DashboardStudioPage'));
const EDAStudioPage = lazy(() => import('./pages/app/EDAStudioPage'));

const NotFoundPage = lazy(() => import('./pages/NotFoundPage'));

// ---------------------------------------------------------------------------
// RequireAuth — route guard for authenticated pages.
//
// BACKEND INTEGRATION POINT:
// Currently checks the in-memory AuthContext flag set by devSignIn().
// When real session/token authentication is implemented, replace the
// `isAuthenticated` check with a proper token validation call from
// authService or the auth context.
// ---------------------------------------------------------------------------

function RequireAuth() {
  const { isAuthenticated, isLoading, sessionError, retrySession } = useAuth();
  const location = useLocation();
  if (isLoading) return <p role="status" className="page-container">Checking your session…</p>;
  if (sessionError) return <div className="page-container" role="alert"><h1>Unable to check your session</h1><p>{sessionError}</p><button onClick={retrySession}>Retry</button></div>;
  if (!isAuthenticated) {
    // Redirect to login, preserving the intended URL for post-login redirect.
    return <Navigate to="/login" state={{ from: location.pathname + location.search }} replace />;
  }
  return <Outlet />;
}

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------

function App() {
  return (
    <AppErrorBoundary><Suspense fallback={<p role="status" className="page-container">Loading page…</p>}><Routes>
      <Route path="/privacy" element={<LegalPage kind="privacy" />} />
      <Route path="/terms" element={<LegalPage kind="terms" />} />
      {/* Public Routes (Approved Cinematic Experience) */}
      <Route element={<AuthLayout />}>
        <Route path="/" element={<LoginPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      </Route>

      {/* Protected Routes (App) — guarded by RequireAuth */}
      <Route element={<RequireAuth />}>
        <Route element={<AppLayout />}>
          <Route path="/dashboard" element={<DashboardPage />} />

          {/* Dataset Management */}
          <Route path="/datasets" element={<DatasetsPage />} />
          {/*
            Phase 2F: Upload must come before /:datasetId so the literal
            string "upload" is not treated as a dataset ID.
          */}
          <Route path="/datasets/upload" element={<DatasetUploadPage />} />
          <Route path="/datasets/:datasetId" element={<DatasetDetailPage />} />
          <Route path="/connections" element={<ConnectionsPage />} />
          <Route path="/data-warehouse" element={<DataWarehousePage />} />

          {/* Analytics */}
          <Route path="/analysis" element={<AnalysisPage />} />
          <Route path="/visualizations" element={<VisualizationsPage />} />
          <Route path="/eda" element={<EDAStudioPage />} />
          <Route path="/insights" element={<InsightsPage />} />
          <Route path="/insights/what-if" element={<InsightsPage subView="what-if" />} />

          {/* Output */}
          <Route path="/reports" element={<ReportsPage />} />
          <Route path="/reports/create" element={<CreateReportPage />} />
          <Route path="/reports/:reportId" element={<ReportDetailPage />} />
          <Route path="/reports/:reportId/edit" element={<ReportBuilderPage />} />

          {/* Phase 23 — New Pages */}
          <Route path="/forecasting" element={<ForecastingWorkbenchPage />} />
          <Route path="/memory" element={<AIMemoryExplorerPage />} />
          <Route path="/dashboard-studio" element={<DashboardStudioPage />} />

          {/* Account */}
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
      </Route>

      {/* Fallback for unknown routes */}
      <Route path="*" element={<NotFoundPage />} />
    </Routes></Suspense></AppErrorBoundary>
  );
}

export default App;
