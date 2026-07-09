import { useState } from "react";
import Header from "./components/Header";
import LoginPage from "./components/LoginPage";
import ProjectsList from "./components/ProjectsList";
import ProjectPage from "./components/ProjectPage";
import { useAuth } from "./context/AuthContext";

export default function App() {
  const { user, loading, logout } = useAuth();
  const [projectId, setProjectId] = useState(null);

  if (loading) {
    return (
      <div className="login-page">
        <div className="spinner" />
      </div>
    );
  }

  if (!user) {
    return <LoginPage />;
  }

  return (
    <>
      <Header user={user} onLogout={logout} />

      {projectId ? (
        <ProjectPage projectId={projectId} onBack={() => setProjectId(null)} />
      ) : (
        <ProjectsList onOpenProject={setProjectId} />
      )}

      <footer className="fs-footer">
        <div className="fs-footer-inner">
          <span className="fs-footer-wordmark">FIFTH SPACE</span>
          <span className="fs-footer-copy">Invoice Agent · San Francisco</span>
        </div>
      </footer>
    </>
  );
}
