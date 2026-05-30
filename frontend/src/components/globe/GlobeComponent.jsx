import React, { useRef, useEffect, useState } from 'react';
import Globe from 'react-globe.gl';

const getWeatherIcon = (cond) => {
    switch (cond) {
        case 'Clear': return '☀️';
        case 'Clouds': return '☁️';
        case 'Rain': return '🌧️';
        case 'Snow': return '❄️';
        case 'Thunderstorm': return '⛈️';
        default: return '🌤️';
    }
};

const tooltip = (html, color = '#22d3ee') =>
    `<div style="background:rgba(15,23,42,0.95);border:1px solid ${color}44;padding:6px 10px;border-radius:6px;color:#e2e8f0;font-size:11px;font-weight:600;backdrop-filter:blur(8px);box-shadow:0 4px 12px rgba(0,0,0,.5);white-space:nowrap;">${html}</div>`;

const GlobeComponent = ({
    threats = [], cameras = [], onCameraSelect, onEventSelect,
    earthquakes = [], flights = [], weather = [],
    lightning = [], ships = [], volcanoes = [], radiation = [],
    maritimeRoutes = [],
    // CMD-CTR world events — plotted as an extra ring layer
    worldEvents = [],
}) => {
    const globeEl = useRef();
    const [dimensions, setDimensions] = useState({
        width: typeof window !== 'undefined' ? window.innerWidth : 1200,
        height: typeof window !== 'undefined' ? window.innerHeight : 800,
    });
    const [isMobile, setIsMobile] = useState(false);

    useEffect(() => {
        const checkMobile = () => {
            const mobile = window.innerWidth < 768;
            setIsMobile(mobile);
            setDimensions({ width: window.innerWidth, height: window.innerHeight });
        };
        checkMobile();

        if (globeEl.current) {
            const controls = globeEl.current.controls();
            controls.autoRotate = true;
            controls.autoRotateSpeed = 0.4;
            controls.enableDamping = true;
            controls.dampingFactor = 0.05;
            controls.rotateSpeed = 0.5;
            controls.zoomSpeed = 0.8;
            controls.minDistance = 100;
            controls.maxDistance = 300;
            globeEl.current.pointOfView({ lat: 20, lng: 0, altitude: 2.5 }, 0);
        }

        const handleResize = () => {
            const mobile = window.innerWidth < 768;
            setIsMobile(mobile);
            setDimensions({ width: window.innerWidth, height: window.innerHeight });
        };
        window.addEventListener('resize', handleResize);
        return () => window.removeEventListener('resize', handleResize);
    }, []);

    // --- Rings ---
    const allRings = [
        ...threats.map(t => ({ lat: t.lat, lng: t.lng, maxR: t.weight * 2, color: t.weight === 5 ? '#ef4444' : '#f97316', prop: 1.5, rep: 1000 })),
        ...cameras.map(c => ({ lat: c.lat, lng: c.lng, maxR: 3, color: '#06b6d4', prop: 1, rep: 1500 })),
        ...earthquakes.map(eq => ({ lat: eq.lat, lng: eq.lng, maxR: eq.mag ? eq.mag * 0.8 : 3, color: '#dc2626', prop: 2, rep: 800 })),
        ...lightning.map(l => ({ lat: l.lat, lng: l.lng, maxR: 1.5, color: '#fef08a', prop: 5, rep: 400 })),
        ...radiation.filter(r => r.alert).map(r => ({ lat: r.lat, lng: r.lng, maxR: 5, color: '#c026d3', prop: 0.5, rep: 2000 })),
        // CMD-CTR real world events — teal rings
        ...worldEvents.filter(e => e.lat && e.lng).map(e => ({ lat: e.lat, lng: e.lng, maxR: 4, color: '#14b8a6', prop: 1.2, rep: 1200 })),
    ];

    // --- Points ---
    const allPoints = [
        ...threats.map(t => ({ lat: t.lat, lng: t.lng, size: 0.2 + t.weight * 0.1, color: t.weight === 5 ? '#ef4444' : '#f97316', alt: 0.01, _type: 'threat', _data: t })),
        ...earthquakes.map(eq => ({ lat: eq.lat, lng: eq.lng, size: eq.mag ? eq.mag / 10 : 0.4, color: '#dc2626', alt: 0, _type: 'earthquake', _data: eq })),
        ...flights.map(f => ({ lat: f.lat, lng: f.lng, size: 0.1, color: '#38bdf8', alt: 0.05 + (f.alt ? f.alt / 100000 : 0), _type: 'flight', _data: f })),
        ...ships.map(s => ({ lat: s.lat, lng: s.lng, size: 0.05, color: '#93c5fd', alt: 0, _type: 'ship', _data: s })),
        // CMD-CTR real world events as teal dots
        ...worldEvents.filter(e => e.lat && e.lng).map(e => ({ lat: e.lat, lng: e.lng, size: 0.25, color: '#2dd4bf', alt: 0.02, _type: 'worldEvent', _data: e })),
    ];

    // --- HTML overlays ---
    const allHtml = [
        ...cameras.map(c => ({ lat: c.lat, lng: c.lng, type: 'camera', data: c })),
        ...weather.map(w => ({ lat: w.lat, lng: w.lng, type: 'weather', data: w })),
        ...volcanoes.map(v => ({ lat: v.lat, lng: v.lng, type: 'volcano', data: v })),
        ...radiation.map(r => ({ lat: r.lat, lng: r.lng, type: 'radiation', data: r })),
    ];

    const handlePointClick = (point) => {
        if (navigator.vibrate) navigator.vibrate(10);
        if (onEventSelect) onEventSelect(point._type, point._data);
    };

    return (
        <div style={{ position: 'relative', width: '100%', height: '100%', overflow: 'hidden', background: '#000' }}>
            <Globe
                ref={globeEl}
                globeImageUrl="//unpkg.com/three-globe/example/img/earth-blue-marble.jpg"
                bumpImageUrl="//unpkg.com/three-globe/example/img/earth-topology.png"
                backgroundColor="rgba(0,0,0,0)"
                width={dimensions.width}
                height={dimensions.height}
                atmosphereColor="#4a90d9"
                atmosphereAltitude={0.2}

                pointsData={allPoints}
                pointAltitude="alt"
                pointColor="color"
                pointRadius="size"
                onPointClick={handlePointClick}
                pointLabel={d => {
                    const labels = {
                        threat: `⚠️ Threat — severity ${d._data.weight} — ${d._data.region || ''}`,
                        earthquake: `🌍 M${d._data.mag?.toFixed(1)} — ${d._data.title || 'Seismic event'}`,
                        flight: `✈️ ${d._data.callsign} (${d._data.country || ''})`,
                        ship: `🚢 ${d._data.type} — MMSI ${d._data.mmsi || ''}`,
                        worldEvent: `📡 ${d._data.title || d._data.category || 'World Event'}`,
                    };
                    return tooltip(labels[d._type] || d._type);
                }}

                ringsData={allRings}
                ringColor="color"
                ringMaxRadius="maxR"
                ringPropagationSpeed="prop"
                ringRepeatPeriod="rep"

                arcsData={maritimeRoutes.map(r => ({
                    startLat: r.startLat, startLng: r.startLng,
                    endLat: r.endLat, endLng: r.endLng,
                    color: r.color, _data: r
                }))}
                arcColor="color"
                arcDashLength={0.4}
                arcDashGap={0.2}
                arcDashAnimateTime={3000}
                arcStroke={0.5}
                onArcClick={arc => { if (onEventSelect) onEventSelect('route', arc._data); }}
                arcLabel={d => tooltip(`⚓ ${d._data.name} — click for details`, d.color)}

                htmlElementsData={allHtml}
                htmlElement={d => {
                    const el = document.createElement('div');
                    el.style.pointerEvents = 'auto';
                    el.style.cursor = 'pointer';

                    if (d.type === 'camera') {
                        el.innerHTML = `
                            <div style="display:flex;flex-direction:column;align-items:center;">
                                <div style="width:24px;height:24px;border-radius:50%;background:rgba(6,182,212,0.2);border:2px solid #22d3ee;display:flex;align-items:center;justify-content:center;animation:pulse 2s infinite;box-shadow:0 0 15px rgba(6,182,212,0.6);">
                                    <svg width="12" height="12" fill="none" stroke="#67e8f9" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"/></svg>
                                </div>
                            </div>`;
                        el.title = `LIVE: ${d.data.name}`;
                        el.onclick = () => { if (navigator.vibrate) navigator.vibrate(10); if (onCameraSelect) onCameraSelect(d.data.id); };
                    } else if (d.type === 'weather') {
                        el.innerHTML = `<div style="font-size:14px;" title="${d.data.name}: ${d.data.temp?.toFixed(1)}°C">${getWeatherIcon(d.data.condition)}</div>`;
                        el.onclick = () => { if (onEventSelect) onEventSelect('weather', d.data); };
                    } else if (d.type === 'volcano') {
                        el.innerHTML = `<div style="font-size:14px;animation:pulse 2s infinite;" title="${d.data.name} (${d.data.status})">🌋</div>`;
                        el.onclick = () => { if (onEventSelect) onEventSelect('volcano', d.data); };
                    } else if (d.type === 'radiation') {
                        const isAlert = d.data.alert;
                        el.innerHTML = `<div style="font-size:${isAlert ? '14px' : '11px'};opacity:${isAlert ? 1 : 0.4};${isAlert ? 'animation:bounce 1s infinite;' : ''}" title="${d.data.cpm} CPM${isAlert ? ' ⚠️ ELEVATED' : ''}">☢️</div>`;
                        el.onclick = () => { if (onEventSelect) onEventSelect('radiation', d.data); };
                    }
                    return el;
                }}
            />
        </div>
    );
};

export default GlobeComponent;
