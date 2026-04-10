import { useMemo, useState } from "react";

import OperationalMap from "./OperationalMap";

export default function NavigationPanel({ route, onRequestRoute }) {
  const [origin, setOrigin] = useState(route.origin || "London");
  const [destination, setDestination] = useState(route.destination || "Cambridge");
  const [travelMode, setTravelMode] = useState(route.travel_mode || "drive");
  const [currentLocation, setCurrentLocation] = useState(null);

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

  async function submit(event) {
    event.preventDefault();
    await onRequestRoute({ origin, destination, travel_mode: travelMode });
  }

  function useCurrentLocation() {
    if (!navigator.geolocation) {
      return;
    }
    navigator.geolocation.getCurrentPosition((position) => {
      setCurrentLocation({
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
      });
      setOrigin(`${position.coords.latitude},${position.coords.longitude}`);
    });
  }

  return (
    <section className="panel navigation-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Navigation</p>
          <h2>Route Layer</h2>
        </div>
      </div>

      <form className="mini-form" onSubmit={submit}>
        <input value={origin} onChange={(event) => setOrigin(event.target.value)} placeholder="Origin or lat,lon" />
        <input value={destination} onChange={(event) => setDestination(event.target.value)} placeholder="Destination" />
        <div className="button-row">
          <select value={travelMode} onChange={(event) => setTravelMode(event.target.value)}>
            <option value="drive">Drive</option>
            <option value="walk">Walk</option>
            <option value="bike">Bike</option>
          </select>
          <button type="button" className="panel-button" onClick={useCurrentLocation}>Use Current</button>
          <button type="submit" className="panel-button">Route</button>
        </div>
      </form>

      <div className="route-card">
        <p><span>Origin</span><strong>{route.origin}</strong></p>
        <p><span>Destination</span><strong>{route.destination}</strong></p>
        <p><span>Mode</span><strong>{route.travel_mode}</strong></p>
        <p><span>Distance</span><strong>{route.distance || "Waiting for route"}</strong></p>
        <p><span>ETA</span><strong>{route.eta || "Waiting for route"}</strong></p>
        <p><span>Provider</span><strong>{route.provider || "Pending"}</strong></p>
      </div>

      <OperationalMap
        markers={routeMarkers}
        selectedId={routeMarkers[1]?.id || routeMarkers[0]?.id}
        routeGeometry={route.geometry || []}
        currentLocation={currentLocation}
        className="operational-map--navigation"
      />
    </section>
  );
}
