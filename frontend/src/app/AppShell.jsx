import { useState } from "react";
import ActionShortcutsPanel from "../components/actions/ActionShortcutsPanel";
import DecisionEnginePanel from "../components/agents/DecisionEnginePanel";
import ConversationPanel from "../components/chat/ConversationPanel";
import MissionPanel from "../components/command/MissionPanel";
import EventsStreamPanel from "../components/dashboard/EventsStreamPanel";
import InfrastructurePanel from "../components/infrastructure/InfrastructurePanel";
import WatchOfficerPanel from "../components/ops/WatchOfficerPanel";
import TopBar from "../components/shell/TopBar";

export default function AppShell(props) {
  const [mobileTab, setMobileTab] = useState("chat");
  const latestAssistantMessage = [...props.messages].reverse().find((m) => m.role === "assistant");

  return (
    <div className="command-center">
      <div className="command-center__bg" />
      <div className="command-center__wash" />
      <TopBar
        mode={props.mode}
        modeReason={props.modeReason}
        voice={props.voice}
        devices={props.devices}
        onModeChange={props.switchMode}
        onOpenIntel={props.openIntelBoard}
      />

      <div className="command-grid" data-mobile-tab={mobileTab}>
        <aside className="rail rail--left">
          <MissionPanel mode={props.mode} onOpenIntel={props.openIntelBoard} />
          <WatchOfficerPanel
            alerts={props.watchAlerts}
            onDismiss={props.dismissAlert}
          />
        </aside>

        <main className="mission-core">
          <div className="mission-core__halo" />
          <ConversationPanel
            messages={props.messages}
            pending={props.pending}
            error={props.error}
            mode={props.mode}
            draft={props.draft}
            voice={props.voice}
            onDraftChange={props.setDraft}
            onSubmit={props.submitQuery}
            onClear={props.clearChat}
            onVoiceStateChange={props.setVoiceFlags}
            onError={props.setError}
          />
          {props.mode === "decision" && (
            <DecisionEnginePanel mode={props.mode} message={latestAssistantMessage} />
          )}
        </main>

        <aside className="rail rail--right">
          <InfrastructurePanel
            nodes={props.nodes}
            onAddNode={props.addNode}
            onSaveNode={props.saveNode}
            onProbeNode={props.probeNodeById}
            onVerifyNode={props.verifyNodeById}
            onDeleteNode={props.removeNode}
          />
          <ActionShortcutsPanel
            actions={props.actions}
            audio={props.audio}
            onRunAction={props.runAction}
            onRunAliasAction={props.runAliasAction}
            onAudioAction={props.applyAudio}
          />
          <EventsStreamPanel logs={props.logs} />
        </aside>
      </div>

      {/* Mobile bottom tab bar — hidden on desktop via CSS */}
      <nav className="mobile-nav">
        <button
          className={`mobile-nav__tab${mobileTab === "missions" ? " mobile-nav__tab--active" : ""}`}
          onClick={() => setMobileTab("missions")}
        >
          <span className="mobile-nav__icon">◈</span>
          <span className="mobile-nav__label">Missions</span>
        </button>
        <button
          className={`mobile-nav__tab${mobileTab === "chat" ? " mobile-nav__tab--active" : ""}`}
          onClick={() => setMobileTab("chat")}
        >
          <span className="mobile-nav__icon">◉</span>
          <span className="mobile-nav__label">Chat</span>
        </button>
        <button
          className={`mobile-nav__tab${mobileTab === "intel" ? " mobile-nav__tab--active" : ""}`}
          onClick={() => setMobileTab("intel")}
        >
          <span className="mobile-nav__icon">◎</span>
          <span className="mobile-nav__label">Intel</span>
        </button>
      </nav>
    </div>
  );
}
