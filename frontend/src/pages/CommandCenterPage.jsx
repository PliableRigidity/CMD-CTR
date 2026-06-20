import { useEffect, useState } from "react";
import AppShell from "../app/AppShell";
import ApiKeyModal from "../components/shell/ApiKeyModal";
import { on401 } from "../lib/api";
import { useCommandCenterData } from "../hooks/useCommandCenterData";

export default function CommandCenterPage() {
  const data = useCommandCenterData();
  const [showApiKey, setShowApiKey] = useState(false);
  const [modal401, setModal401] = useState(false);

  useEffect(() => {
    on401(() => {
      setModal401(true);
      setShowApiKey(true);
    });
  }, []);

  function handleOpenSettings() {
    setModal401(false);
    setShowApiKey(true);
  }

  function handleCloseModal() {
    setShowApiKey(false);
    setModal401(false);
  }

  return (
    <>
      <AppShell {...data} onOpenSettings={handleOpenSettings} />
      {showApiKey && (
        <ApiKeyModal onClose={handleCloseModal} triggered401={modal401} />
      )}
    </>
  );
}
