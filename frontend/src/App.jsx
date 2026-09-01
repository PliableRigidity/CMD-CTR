import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import CommandCenterPage from "./pages/CommandCenterPage";
import HardwareBoardPage from "./pages/HardwareBoardPage";
import IntelBoardPage from "./pages/IntelBoardPage";
import KnowledgeGraphPage from "./pages/KnowledgeGraphPage";
import ProjectMemoryPage from "./pages/ProjectMemoryPage";
import VoiceDiagnosticsPage from "./pages/VoiceDiagnosticsPage";
import WorkspacePage from "./pages/WorkspacePage";
import PlannerPage from "./pages/PlannerPage";
import WorkflowsPage from "./pages/WorkflowsPage";
import Brain63Page from "./pages/Brain63Page";
import KosinePage from "./pages/KosinePage";
import CognitiveGraphPage from "./pages/CognitiveGraphPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Primary navigation */}
        <Route path="/" element={<CommandCenterPage />} />
        <Route path="/assistant" element={<CommandCenterPage />} />
        <Route path="/hardware" element={<HardwareBoardPage />} />
        <Route path="/intel" element={<IntelBoardPage />} />

        {/* Primary aliases — user-facing names */}
        <Route path="/projects" element={<WorkspacePage />} />
        <Route path="/nodes" element={<CommandCenterPage />} />
        <Route path="/apps" element={<CommandCenterPage />} />

        {/* Advanced / Developer Mode boards */}
        <Route path="/knowledge" element={<KnowledgeGraphPage />} />
        <Route path="/graph" element={<KnowledgeGraphPage />} />
        <Route path="/memory" element={<ProjectMemoryPage />} />
        <Route path="/workspace" element={<WorkspacePage />} />
        <Route path="/twin" element={<WorkspacePage />} />
        <Route path="/planner" element={<PlannerPage />} />
        <Route path="/workflows" element={<WorkflowsPage />} />
        <Route path="/brain63" element={<Brain63Page />} />
        <Route path="/kosine" element={<KosinePage />} />
        <Route path="/cognitive" element={<CognitiveGraphPage />} />
        <Route path="/voice" element={<VoiceDiagnosticsPage />} />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
