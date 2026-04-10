import { useEffect, useMemo, useState } from "react";

import { fetchWorldEvents } from "../lib/api";
import { DEFAULT_REGION_LABELS } from "../types/world";

export function useIntelBoardData() {
  const [events, setEvents] = useState([]);
  const [selectedEventId, setSelectedEventId] = useState(null);
  const [category, setCategory] = useState("");
  const [country, setCountry] = useState("United Kingdom");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [currentLocation, setCurrentLocation] = useState(null);

  async function load(next = {}) {
    setLoading(true);
    setError("");
    try {
      const requestedCategory = next.category ?? category;
      const requestedCountry = next.country ?? country;
      const data = await fetchWorldEvents({
        live: true,
        category: requestedCategory || undefined,
      });
      setEvents(data);
      setCategory(requestedCategory);
      setCountry(requestedCountry);
      const visible = filterEvents(data, requestedCountry);
      setSelectedEventId((current) => (current && visible.some((item) => item.id === current) ? current : visible[0]?.id ?? null));
    } catch (loadError) {
      setError(loadError.message || "Failed to load world events.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (!navigator.geolocation) {
      return undefined;
    }

    const watchId = navigator.geolocation.watchPosition(
      (position) => {
        setCurrentLocation({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
        });
      },
      () => {
        setCurrentLocation(null);
      },
      { enableHighAccuracy: false, maximumAge: 30000, timeout: 15000 },
    );

    return () => navigator.geolocation.clearWatch(watchId);
  }, []);

  const filteredEvents = useMemo(() => filterEvents(events, country), [events, country]);

  const selectedEvent = useMemo(
    () => filteredEvents.find((item) => item.id === selectedEventId) || filteredEvents[0] || null,
    [filteredEvents, selectedEventId],
  );

  const countries = useMemo(
    () => {
      const dynamic = [...new Set(events.map((item) => (item.is_global ? "Global" : item.primary_country || item.country)).filter(Boolean))];
      const merged = [...DEFAULT_REGION_LABELS, ...dynamic.filter((item) => !DEFAULT_REGION_LABELS.includes(item))];
      return merged;
    },
    [events],
  );

  return {
    events: filteredEvents,
    allEvents: events,
    selectedEvent,
    selectedEventId,
    category,
    country,
    countries,
    loading,
    error,
    currentLocation,
    setSelectedEventId,
    refresh: load,
  };
}

function filterEvents(events, country) {
  if (!country || country === "All regions") {
    return events;
  }
  if (country === "Global") {
    return events.filter((item) => item.is_global);
  }
  return events.filter((item) => (item.primary_country || item.country) === country);
}
