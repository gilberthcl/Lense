import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { Tenant } from "../lib/types";
import { useToast } from "../components/Toast";
import { PageHeader } from "../components/Layout";
import { IconClients, IconPlus } from "../components/icons";
import ClientGrid from "../components/ClientGrid";
import ClientWizard from "../components/client/ClientWizard";
import { Button } from "../components/ui";

export default function ClientsPage() {
  const toast = useToast();
  const [clients, setClients] = useState<Tenant[] | null>(null);
  const [showWizard, setShowWizard] = useState(false);

  const load = () =>
    api
      .listTenants()
      .then(setClients)
      .catch((e: ApiError) => {
        toast.error(e.message);
        setClients([]);
      });

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div>
      <PageHeader
        icon={<IconClients width={22} height={22} />}
        title="Clients"
        description="Clients are global — created once and shared across every LENS module. Each is a fully isolated workspace; knowledge, hunts, datasets, and findings never cross between clients."
        actions={
          <Button variant="primary" onClick={() => setShowWizard((s) => !s)}>
            <IconPlus width={16} height={16} /> {showWizard ? "Close" : "New Client"}
          </Button>
        }
      />

      {showWizard && (
        <ClientWizard
          onCancel={() => setShowWizard(false)}
          onCreated={() => {
            setShowWizard(false);
            load();
          }}
        />
      )}

      <ClientGrid clients={clients} emptyHint="No clients yet. Create one to get started." />
    </div>
  );
}
