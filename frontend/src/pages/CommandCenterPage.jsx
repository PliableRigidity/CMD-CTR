import AppShell from "../app/AppShell";
import { useCommandCenterData } from "../hooks/useCommandCenterData";

export default function CommandCenterPage() {
  const data = useCommandCenterData();
  return <AppShell {...data} />;
}
