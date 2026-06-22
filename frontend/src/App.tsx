import { Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import TenantsPage from "./pages/TenantsPage";
import TenantDashboard from "./pages/TenantDashboard";
import HuntView from "./pages/HuntView";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<TenantsPage />} />
        <Route path="/tenants/:tid" element={<TenantDashboard />} />
        <Route path="/tenants/:tid/hunts/:hid" element={<HuntView />} />
        <Route
          path="*"
          element={
            <div className="text-center text-slate-500">Page not found.</div>
          }
        />
      </Routes>
    </Layout>
  );
}
