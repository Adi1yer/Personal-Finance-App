import { Routes, Route, Navigate } from "react-router-dom";
import AppShell from "./components/AppShell";
import GoogleDriveQuitBackup from "./components/GoogleDriveQuitBackup";
import ProtectedRoute from "./components/ProtectedRoute";
import DashboardPage from "./pages/DashboardPage";
import AccountsPage from "./pages/AccountsPage";
import RegisterPage from "./pages/RegisterPage";
import ReconcilePage from "./pages/ReconcilePage";
import ReportsPage from "./pages/ReportsPage";
import SettingsPage from "./pages/SettingsPage";
import GoalsPage from "./pages/GoalsPage";
import AdvisorPage from "./pages/AdvisorPage";
import DuplicatesPage from "./pages/DuplicatesPage";
import RulesPage from "./pages/RulesPage";
import LoginPage from "./pages/LoginPage";
import SignUpPage from "./pages/SignUpPage";
import ForgotPasswordPage from "./pages/ForgotPasswordPage";

export default function App() {
  return (
    <>
      <GoogleDriveQuitBackup />
      <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/login/register" element={<SignUpPage />} />
      <Route path="/login/forgot-password" element={<ForgotPasswordPage />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<AppShell />}>
          <Route index element={<DashboardPage />} />
          <Route path="accounts" element={<AccountsPage />} />
          <Route path="register" element={<RegisterPage />} />
          <Route path="goals" element={<GoalsPage />} />
          <Route path="advisor" element={<AdvisorPage />} />
          <Route path="review/duplicates" element={<DuplicatesPage />} />
          <Route path="rules" element={<RulesPage />} />
          <Route path="reconcile" element={<ReconcilePage />} />
          <Route path="reports" element={<ReportsPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    </>
  );
}
