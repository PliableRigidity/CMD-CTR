import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet.markercluster";

function getColor(category, severity) {
  if (severity === "high") return "#ff7e8a";
  if (category === "tech") return "#63d2ff";
  if (category === "economy") return "#ffc857";
  if (category === "science") return "#9cf8d2";
  return "#d5e7ff";
}

function buildLeafletIcon(color, selected = false) {
  return L.divIcon({
    className: "leaflet-pin-wrapper",
    html: `<span class="leaflet-pin${selected ? " is-selected" : ""}" style="background:${color}"></span>`,
    iconSize: [selected ? 22 : 18, selected ? 22 : 18],
    iconAnchor: [selected ? 11 : 9, selected ? 11 : 9],
  });
}

function buildClusterIcon(cluster) {
  const count = cluster.getChildCount();
  return L.divIcon({
    className: "leaflet-cluster-wrapper",
    html: `<span class="leaflet-cluster-pin">${count}</span>`,
    iconSize: [40, 40],
    iconAnchor: [20, 20],
  });
}

export default function OperationalMap({
  markers = [],
  selectedId,
  onSelect,
  routeGeometry = [],
  currentLocation = null,
  className = "",
  defaultCenter = [20, 0],
  defaultZoom = 2,
}) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const clusterGroupRef = useRef(null);
  const overlayLayerRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return undefined;

    const map = L.map(containerRef.current, {
      zoomControl: true,
      attributionControl: true,
      center: defaultCenter,
      zoom: defaultZoom,
      worldCopyJump: true,
    });

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap contributors",
      maxZoom: 19,
    }).addTo(map);

    const clusterGroup = L.markerClusterGroup({
      showCoverageOnHover: false,
      spiderfyOnMaxZoom: true,
      disableClusteringAtZoom: 6,
      iconCreateFunction: buildClusterIcon,
    });
    const overlayLayer = L.layerGroup();

    map.addLayer(clusterGroup);
    map.addLayer(overlayLayer);

    map.whenReady(() => {
      window.setTimeout(() => {
        map.invalidateSize();
      }, 0);
    });

    const resizeObserver = new ResizeObserver(() => {
      map.invalidateSize(false);
    });
    resizeObserver.observe(containerRef.current);

    mapRef.current = map;
    clusterGroupRef.current = clusterGroup;
    overlayLayerRef.current = overlayLayer;

    return () => {
      resizeObserver.disconnect();
      map.remove();
      mapRef.current = null;
      clusterGroupRef.current = null;
      overlayLayerRef.current = null;
    };
  }, [defaultCenter, defaultZoom]);

  useEffect(() => {
    const map = mapRef.current;
    const clusterGroup = clusterGroupRef.current;
    const overlayLayer = overlayLayerRef.current;
    if (!map || !clusterGroup || !overlayLayer) return;

    clusterGroup.clearLayers();
    overlayLayer.clearLayers();

    const bounds = [];

    markers.forEach((item) => {
      if (typeof item.latitude !== "number" || typeof item.longitude !== "number") return;
      const marker = L.marker([item.latitude, item.longitude], {
        icon: buildLeafletIcon(getColor(item.category, item.severity), selectedId === item.id),
      });

      marker.on("click", () => onSelect?.(item.id));
      marker.bindPopup(`
        <strong>${item.title}</strong><br/>
        ${item.country || "Unknown region"}<br/>
        ${item.summary || ""}
      `);

      clusterGroup.addLayer(marker);
      bounds.push([item.latitude, item.longitude]);
    });

    if (currentLocation?.latitude && currentLocation?.longitude) {
      const userMarker = L.circleMarker([currentLocation.latitude, currentLocation.longitude], {
        radius: 8,
        color: "#07111d",
        weight: 2,
        fillColor: "#9cf8d2",
        fillOpacity: 1,
      });
      userMarker.bindPopup("Current location");
      overlayLayer.addLayer(userMarker);
      bounds.push([currentLocation.latitude, currentLocation.longitude]);
    }

    if (routeGeometry?.length) {
      const polylinePoints = routeGeometry
        .filter((coordinate) => Array.isArray(coordinate) && coordinate.length >= 2)
        .map((coordinate) => [coordinate[1], coordinate[0]]);

      if (polylinePoints.length) {
        const polyline = L.polyline(polylinePoints, {
          color: "#63d2ff",
          weight: 4,
          opacity: 0.92,
        });
        overlayLayer.addLayer(polyline);
        bounds.push(...polylinePoints);
      }
    }

    if (bounds.length) {
      map.fitBounds(bounds, { padding: [36, 36], maxZoom: routeGeometry?.length ? 12 : 5 });
    }
  }, [markers, selectedId, onSelect, routeGeometry, currentLocation]);

  useEffect(() => {
    const map = mapRef.current;
    const clusterGroup = clusterGroupRef.current;
    if (!map || !clusterGroup || !selectedId) return;

    const selected = markers.find((item) => item.id === selectedId);
    if (selected && typeof selected.latitude === "number" && typeof selected.longitude === "number") {
      map.flyTo([selected.latitude, selected.longitude], 4, { duration: 0.8 });
      clusterGroup.eachLayer((layer) => {
        const latLng = layer.getLatLng?.();
        if (latLng && latLng.lat === selected.latitude && latLng.lng === selected.longitude) {
          layer.openPopup?.();
        }
      });
    }
  }, [markers, selectedId]);

  return (
    <div className="operational-map-shell">
      <div className="map-status map-status--success">
        <strong>Leaflet + OpenStreetMap</strong>
        <span>Free local-first basemap active. Routing overlays and world-event markers are live.</span>
      </div>
      <div className={`operational-map leaflet-map ${className}`.trim()} ref={containerRef} />
    </div>
  );
}
