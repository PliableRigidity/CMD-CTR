import ActionShortcutsPanel from "../components/actions/ActionShortcutsPanel";
import DecisionEnginePanel from "../components/agents/DecisionEnginePanel";
import ConversationPanel from "../components/chat/ConversationPanel";
import MissionPanel from "../components/command/MissionPanel";
import EventsStreamPanel from "../components/dashboard/EventsStreamPanel";
import DevicesPanel from "../components/devices/DevicesPanel";
import NavigationPanel from "../components/maps/NavigationPanel";
import TopBar from "../components/shell/TopBar";
import VoiceStatusPill from "../components/voice/VoiceStatusPill";

export default function AppShell(props) {
  const latestAssistantMessage = [...props.messages].reverse().find((message) => message.role === "assistant");

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

      <div className="command-grid">
        <aside className="rail rail--left">
          <MissionPanel mode={props.mode} route={props.route} onOpenIntel={props.openIntelBoard} />
          <NavigationPanel route={props.route} onRequestRoute={props.requestRoute} />
        </aside>

        <main className="mission-core">
          <div className="mission-core__halo" />
          <VoiceStatusPill
            voice={props.voice}
            pending={props.pending}
            draft={props.draft}
            onDraftChange={props.setDraft}
            onError={props.setError}
            onVoiceStateChange={props.setVoiceFlags}
          />
          <ConversationPanel
            messages={props.messages}
            pending={props.pending}
            error={props.error}
            mode={props.mode}
            draft={props.draft}
            onDraftChange={props.setDraft}
            onSubmit={props.submitQuery}
          />
        </main>

        <aside className="rail rail--right">
          <DevicesPanel devices={props.devices} audio={props.audio} />
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

      <DecisionEnginePanel mode={props.mode} message={latestAssistantMessage} />
    </div>
  );
}
