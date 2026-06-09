import { useMemo, useState } from "react";
import OperationalMap from "./OperationalMap";

export default function NavigationPanel({ route, onRequestRoute }) {
  const [open, setOpen] = useState(false);
  const [origin, setOrigin] = useState(route.origin || "London");
  const [destination, setDestination] = useState(route.destination || "Cambridge");
  const [travelMode, setTravelMode] = useState(route.travel_mode || "drive");

  const routeMarkers = useMemo(() => {
    const markers = [];
    if (typeof route.origin_lon === "number" && typeof route.origin_lat === "number") {
      markers.push({
        id: "route-origin",
        title: route.origin || "Origin",
        country: "Origin",
        category: "navigation",
        severity: "low",
        longitude: route.origin_lon,
        latitude: route.origin_lat,
      });
    }
    if (typeof route.destination_lon === "number" && typeof route.destination_lat === "number") {
      markers.push({
        id: "route-destination",
        title: route.destination || "Destination",
        country: "Destination",
        category: "navigation",
        severity: "medium",
        longitude: route.destination_lon,
        latitude: route.destination_lat,
      });
    }
    return markers;
  }, [route]);

  async function submit(e) {
    e.preventDefault();
    await onRequestRoute({ origin, destination, travel_mode: travelMode });
  }

  function useCurrentLocation() {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition((pos) => {
      setOrigin(`${pos.coords.latitude},${pos.coords.longitude}`);
    });
  }

  return (
    <section className="panel nav-panel">
      <button type="button" className="nav-panel__toggle" onClick={() => setOpen(!open)}>
        <div>
          <p className="eyebrow">Navigation</p>
          <h2>Route Layer</h2>
        </div>
        <span className="nav-toggle-icon">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="nav-panel__body">
          <form className="mini-form" onSubmit={submit} style={{ marginBottom: "10px" }}>
            <input
              value={origin}
              onChange={(e) => setOrigin(e.target.value)}
              placeholder="Origin or lat,lon"
            />
            <input
              value={destination}
              onChange={(e) => setDestination(e.target.value)}
              placeholder="Destination"
            />
            <div className="button-row">
              <select value={travelMode} onChange={(e) => setTravelMode(e.target.value)}>
                <option value="drive">Drive</option>
                <option value="walk">Walk</option>
                <option value="bike">Bike</option>
              </select>
              <button type="button" className="panel-button" onClick={useCurrentLocation}>GPS</button>
              <button type="submit" className="panel-button">Route</button>
            </div>
          </form>

          {route.distance && (
            <div className="route-summary">
              <span>{route.origin} → {route.destination}</span>
              <span>{route.distance} · {route.eta}</span>
            </div>
          )}

          <OperationalMap
            markers={routeMarkers}
            selectedId={routeMarkers[1]?.id ?? routeMarkers[0]?.id}
            routeGeometry={route.geometry ?? []}
            currentLocation={null}
            className="operational-map--navigation"
          />
        </div>
      )}
    </section>
  );
}
