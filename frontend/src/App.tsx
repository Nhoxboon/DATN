import { Navigate, Route, Routes } from 'react-router-dom'
import { ProtectedRoute } from './components/auth/ProtectedRoute'
import { LoginPage } from './pages/LoginPage'
import { SignUpPage } from './pages/SignUpPage'
import { ForgotPasswordPage } from './pages/ForgotPasswordPage'
import { ChangePasswordPage } from './pages/ChangePasswordPage'
import { ResetPasswordPage } from './pages/ResetPasswordPage'
import { AuthCallbackPage } from './pages/AuthCallbackPage'
import { DashboardPage } from './pages/DashboardPage'
import { NotebookEditorPage } from './pages/NotebookEditorPage'
import { useTheme } from './hooks/useTheme'
import { useAuth } from './hooks/useAuth'

function RootRedirect() {
  const { loading, user } = useAuth()

  if (loading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background text-sm font-medium text-muted">
        Loading workspace...
      </main>
    )
  }

  return <Navigate to={user ? '/dashboard' : '/login'} replace />
}

function App() {
  useTheme()

  return (
    <Routes>
      <Route path="/" element={<RootRedirect />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/sign-up" element={<SignUpPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/auth/callback" element={<AuthCallbackPage />} />
      <Route
        path="/change-password"
        element={
          <ProtectedRoute>
            <ChangePasswordPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/dashboard"
        element={
          <ProtectedRoute>
            <DashboardPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/notebooks/:notebookId"
        element={
          <ProtectedRoute>
            <NotebookEditorPage />
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  )
}

export default App
