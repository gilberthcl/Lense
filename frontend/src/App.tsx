import { Navigate, Route, Routes, useParams } from "react-router-dom";
import { Layout } from "./components/Layout";
import ClientsPage from "./pages/ClientsPage";
import ClientWorkspace from "./pages/ClientWorkspace";
import StructuredHunts from "./pages/StructuredHunts";
import HuntView from "./pages/HuntView";
import ConfigPage from "./pages/ConfigPage";
import ModulePlaceholder from "./pages/ModulePlaceholder";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/structured-hunts" replace />} />

        {/* Live module */}
        <Route path="/structured-hunts" element={<StructuredHunts />} />
        {/* A client opened in the context of the Structured Hunts module */}
        <Route
          path="/structured-hunts/clients/:tid"
          element={<ClientWorkspace moduleId="structured-hunts" />}
        />
        <Route path="/structured-hunts/clients/:tid/hunts/:hid" element={<HuntView />} />

        {/* Global clients */}
        <Route path="/clients" element={<ClientsPage />} />
        <Route path="/clients/:tid" element={<ClientWorkspace />} />
        <Route path="/clients/:tid/hunts/:hid" element={<HuntView />} />

        {/* Future modules */}
        <Route
          path="/modules/unstructured-hunts"
          element={<ModulePlaceholder moduleId="unstructured-hunts" />}
        />
        <Route
          path="/modules/threat-reviews"
          element={<ModulePlaceholder moduleId="threat-reviews" />}
        />
        <Route
          path="/modules/intel-weekly"
          element={<ModulePlaceholder moduleId="intel-weekly" />}
        />

        <Route path="/config" element={<ConfigPage />} />

        {/* Legacy redirects */}
        <Route path="/tenants" element={<Navigate to="/clients" replace />} />
        <Route path="/tenants/:tid" element={<LegacyClientRedirect />} />

        <Route
          path="*"
          element={<div className="text-center text-slate-500">Page not found.</div>}
        />
      </Routes>
    </Layout>
  );
}

function LegacyClientRedirect() {
  const { tid } = useParams();
  return <Navigate to={`/clients/${tid}`} replace />;
}
