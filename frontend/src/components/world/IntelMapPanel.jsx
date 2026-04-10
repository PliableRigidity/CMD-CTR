import OperationalMap from "../maps/OperationalMap";

export default function IntelMapPanel({ events, selectedEventId, onSelect, currentLocation }) {
  return (
    <section className="intel-map-shell panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Geopolitical Layer</p>
          <h2>World Intel Board</h2>
        </div>
      </div>
      <OperationalMap
        markers={events}
        selectedId={selectedEventId}
        onSelect={onSelect}
        currentLocation={currentLocation}
        className="operational-map--intel"
        defaultCenter={[54.5, -2.5]}
        defaultZoom={5}
      />
    </section>
  );
}
