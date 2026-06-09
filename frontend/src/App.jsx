import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import CommandCenterPage from "./pages/CommandCenterPage";
import IntelBoardPage from "./pages/IntelBoardPage";
import VoiceDiagnosticsPage from "./pages/VoiceDiagnosticsPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<CommandCenterPage />} />
        <Route path="/intel" element={<IntelBoardPage />} />
        <Route path="/voice" element={<VoiceDiagnosticsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
