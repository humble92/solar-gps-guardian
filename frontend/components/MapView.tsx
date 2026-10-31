"use client";
import { useEffect, useRef } from "react";
import "leaflet/dist/leaflet.css";

// Self-contained pin: Leaflet's bundled marker-icon.png 404s under Next.js
// (images in node_modules are not served), so the location marker is an
// inline divIcon styled in globals.css (.sg-pin). No image assets needed.
const PIN_SVG = (storm: boolean) =>
  `<span class="sg-pin${storm ? " storm" : ""}"><span class="sg-pin-dot"></span></span>`;

function lineColor(storm: boolean, level?: string) {
  if (storm || level === "CRITICAL") return "#f87171";
  if (level === "LOW") return "#2dd4bf";
  return "#f59e0b";
}

export default function MapView({ center, route, markers, storm, routeLevel, zoom }: {
  center: [number, number];
  route?: [number, number][];
  markers?: { lat: number; lon: number; label: string }[];
  storm?: boolean;
  routeLevel?: string;
  zoom?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const mapRef = useRef<unknown>(null);
  const layerRef = useRef<unknown>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const L = (await import("leaflet")) as any;
      if (cancelled || !ref.current) return;
      if (!mapRef.current) {
        const map = L.map(ref.current).setView(center, 9);
        L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",
          { attribution: "© OpenStreetMap contributors" }).addTo(map);
        layerRef.current = L.layerGroup().addTo(map);
        mapRef.current = map;
      }
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const map = mapRef.current as any;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const layer = layerRef.current as any;
      layer.clearLayers(); // never accumulate markers/routes across renders
      (markers || []).forEach((m) =>
        L.marker([m.lat, m.lon], {
          icon: L.divIcon({ className: "", html: PIN_SVG(!!storm), iconSize: [26, 26], iconAnchor: [13, 13] }),
          title: m.label,
        }).addTo(layer).bindPopup(m.label));
      if (route && route.length) {
        const latLngs = route.map(([lon, lat]) => [lat, lon]);
        L.polyline(latLngs, { color: lineColor(!!storm, routeLevel), weight: 4 }).addTo(layer);
        map.fitBounds(latLngs, { padding: [28, 28] });
      } else {
        map.setView(center, zoom ?? Math.max(map.getZoom(), 7));
      }
      if (storm) {
        // Visible storm footprint so the simulate toggle changes the map too.
        L.circle(center, { radius: 60000, color: "#f87171", weight: 2,
          dashArray: "8 6", fillColor: "#f87171", fillOpacity: 0.08 }).addTo(layer);
      }
    })();
    return () => { cancelled = true; };
  }, [center, route, markers, storm, routeLevel, zoom]);

  return <div ref={ref} style={{ height: 380, borderRadius: 12, overflow: "hidden" }} />;
}
