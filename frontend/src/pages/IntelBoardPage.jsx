import { Link } from "react-router-dom";

import IntelMapPanel from "../components/world/IntelMapPanel";
import EventFeed from "../components/world/EventFeed";
import { useIntelBoardData } from "../hooks/useIntelBoardData";

export default function IntelBoardPage() {
  const intel = useIntelBoardData();

  return (
    <div className="intel-page">
      <header className="intel-topbar panel">
        <div>
          <p className="eyebrow">World Intel Board</p>
          <h1>Global Monitor</h1>
        </div>
        <div className="button-row">
          <Link className="panel-button intel-link" to="/">Return to Command Center</Link>
        </div>
      </header>

      <div className="intel-layout">
        <IntelMapPanel
          events={intel.events}
          selectedEventId={intel.selectedEventId}
          onSelect={intel.setSelectedEventId}
          currentLocation={intel.currentLocation}
        />
        <EventFeed
          events={intel.events}
          selectedEventId={intel.selectedEventId}
          onSelect={intel.setSelectedEventId}
          loading={intel.loading}
          error={intel.error}
          category={intel.category}
          country={intel.country}
          countries={intel.countries}
          onRefresh={intel.refresh}
        />
      </div>
    </div>
  );
}
