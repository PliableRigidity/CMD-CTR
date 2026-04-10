from __future__ import annotations

import re

import httpx

from backend.app.models.maps import RouteRequest, RouteResponse


class MapsService:
    async def get_route(self, request: RouteRequest) -> RouteResponse:
        origin = await self._resolve_location(request.origin)
        destination = await self._resolve_location(request.destination)

        profile = {"drive": "driving", "walk": "foot", "bike": "bike"}.get(request.travel_mode, "driving")
        url = (
            f"https://router.project-osrm.org/route/v1/{profile}/"
            f"{origin['lon']},{origin['lat']};{destination['lon']},{destination['lat']}?overview=full&geometries=geojson"
        )
        async with httpx.AsyncClient(timeout=20.0, headers={"User-Agent": "AssistantCommandCenter/1.0"}) as client:
            response = await client.get(url)
            response.raise_for_status()
        data = response.json()
        route = data["routes"][0]
        return RouteResponse(
            origin=origin["label"],
            destination=destination["label"],
            travel_mode=request.travel_mode,
            distance=f"{route['distance'] / 1000:.1f} km",
            eta=f"{round(route['duration'] / 60)} min",
            provider="osrm+osm",
            notes=[
                "Geocoded with OpenStreetMap search.",
                "Routed with the public OSRM service.",
            ],
            origin_lat=origin["lat"],
            origin_lon=origin["lon"],
            destination_lat=destination["lat"],
            destination_lon=destination["lon"],
            geometry=route.get("geometry", {}).get("coordinates", []),
        )

    async def _resolve_location(self, value: str) -> dict:
        coord_match = re.match(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$", value)
        if coord_match:
            lat = float(coord_match.group(1))
            lon = float(coord_match.group(2))
            return {"label": value, "lat": lat, "lon": lon}

        async with httpx.AsyncClient(
            timeout=20.0,
            headers={"User-Agent": "AssistantCommandCenter/1.0 (local route client)"},
            follow_redirects=True,
        ) as client:
            response = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": value, "format": "jsonv2", "limit": 1},
            )
            response.raise_for_status()
        results = response.json()
        if not results:
            raise ValueError(f"Could not resolve location: {value}")
        match = results[0]
        return {
            "label": match.get("display_name", value),
            "lat": float(match["lat"]),
            "lon": float(match["lon"]),
        }
