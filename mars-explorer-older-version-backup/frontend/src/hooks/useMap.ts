/** MARS EXPLORER - Map Hook */
import { useEffect, useRef, useState, useCallback } from 'react';
import { Map, View, Feature, Overlay } from 'ol';
import { fromLonLat, toLonLat } from 'ol/proj';
import { Point } from 'ol/geom';
import { Style, Circle, Fill, Stroke, Text } from 'ol/style';
import { Vector as VectorLayer, VectorSource } from 'ol/layer';
import { Vector as VectorSource } from 'ol/source';
import { Coordinate } from '../types';
import { MARS_PROJECTION } from '../config/marsProjection';
import { createMarsMap, destroyMap, type MapInstance } from '../services/marsMapService';

export interface UseMapOptions {
  target: string | HTMLElement;
  initialCenter?: Coordinate;
  initialZoom?: number;
  onCenterChange?: (center: Coordinate) => void;
  onZoomChange?: (zoom: number) => void;
  onClick?: (coordinate: Coordinate) => void;
}

export interface UseMapReturn {
  mapInstance: MapInstance | null;
  center: Coordinate;
  zoom: number;
  resolution: number;
  animateTo: (coord: Coordinate, zoom?: number) => void;
  setBaseLayer: (layerId: string) => void;
  toggleOverlay: (layerId: string, visible?: boolean) => void;
  setLayerOpacity: (layerId: string, opacity: number) => void;
  addMarker: (id: string, coordinate: Coordinate, label?: string) => void;
  removeMarker: (id: string) => void;
  clearMarkers: () => void;
  exportState: () => any;
  importState: (state: any) => void;
}

export function useMap({
  target,
  initialCenter = { longitude: 0, latitude: 0 },
  initialZoom = 2,
  onCenterChange,
  onZoomChange,
  onClick,
}: UseMapOptions): UseMapReturn {
  const mapRef = useRef<MapInstance | null>(null);
  const [center, setCenter] = useState<Coordinate>(initialCenter);
  const [zoom, setZoom] = useState<number>(initialZoom);
  const [resolution, setResolution] = useState<number>(0);
  const markersRef = useRef<Map<string, Feature>>(new Map());
  const markersLayerRef = useRef<VectorLayer<VectorSource>>();
  const overlayRef = useRef<Overlay>();

  // Initialize map
  useEffect(() => {
    const instance = createMarsMap(target);
    mapRef.current = instance;

    // Create markers layer
    const markersSource = new VectorSource();
    const markersLayer = new VectorLayer({
      source: markersSource,
      zIndex: 1000,
      style: (feature) => {
        const label = feature.get('label');
        return new Style({
          image: new Circle({
            radius: 8,
            fill: new Fill({ color: '#e94560' }),
            stroke: new Stroke({ color: '#fff', width: 2 }),
          }),
          text: label ? new Text({
            text: label,
            offsetY: -20,
            font: '12px Space Grotesk',
            fill: new Fill({ color: '#fff' }),
            stroke: new Stroke({ color: '#000', width: 3 }),
          }) : undefined,
        });
      },
    });
    markersLayerRef.current = markersLayer;
    instance.map.addLayer(markersLayer);

    // Set initial view
    const projCenter = fromLonLat([initialCenter.longitude, initialCenter.latitude], MARS_PROJECTION);
    instance.view.setCenter(projCenter);
    instance.view.setZoom(initialZoom);

    // Event listeners
    instance.view.on('change:center', () => {
      const c = instance.view.getCenter();
      if (c) {
        const [lon, lat] = toLonLat(c, MARS_PROJECTION);
        const newCenter = { longitude: lon, latitude: lat };
        setCenter(newCenter);
        onCenterChange?.(newCenter);
      }
    });

    instance.view.on('change:resolution', () => {
      const res = instance.view.getResolution();
      if (res !== undefined) {
        setResolution(res);
      }
    });

    instance.view.on('change:zoom', () => {
      const z = instance.view.getZoom();
      if (z !== undefined) {
        setZoom(z);
        onZoomChange?.(z);
      }
    });

    // Click handler
    if (onClick) {
      instance.map.on('singleclick', (evt) => {
        const coord = toLonLat(evt.coordinate, MARS_PROJECTION);
        onClick({ longitude: coord[0], latitude: coord[1] });
      });
    }

    return () => {
      instance.map.un('singleclick');
      instance.view.un('change:center');
      instance.view.un('change:resolution');
      instance.view.un('change:zoom');
    };
  }, [target, initialCenter, initialZoom, onCenterChange, onZoomChange, onClick]);

  // Animation
  const animateTo = useCallback((coord: Coordinate, zoomLevel?: number) => {
    if (!mapRef.current) return;
    const projCenter = fromLonLat([coord.longitude, coord.latitude], MARS_PROJECTION);
    mapRef.current.view.animate({
      center: projCenter,
      zoom: zoomLevel ?? mapRef.current.view.getZoom(),
      duration: 1000,
    });
  }, []);

  // Layer controls
  const setBaseLayer = useCallback((layerId: string) => {
    if (!mapRef.current) return;
    mapRef.current.baseLayers.forEach((layer, id) => {
      layer.setVisible(id === layerId);
    });
  }, []);

  const toggleOverlay = useCallback((layerId: string, visible?: boolean) => {
    if (!mapRef.current) return;
    const layer = mapRef.current.overlayLayers.get(layerId);
    if (layer) {
      layer.setVisible(visible ?? !layer.getVisible());
    }
  }, []);

  const setLayerOpacity = useCallback((layerId: string, opacity: number) => {
    if (!mapRef.current) return;
    const layer = mapRef.current.baseLayers.get(layerId) || mapRef.current.overlayLayers.get(layerId);
    if (layer) {
      layer.setOpacity(Math.max(0, Math.min(1, opacity)));
    }
  }, []);

  // Markers
  const addMarker = useCallback((id: string, coordinate: Coordinate, label?: string) => {
    if (!markersLayerRef.current) return;
    
    const feature = new Feature({
      geometry: new Point(fromLonLat([coordinate.longitude, coordinate.latitude], MARS_PROJECTION)),
      label,
      id,
    });
    feature.setId(id);
    markersRef.current.set(id, feature);
    markersLayerRef.current.getSource()?.addFeature(feature);
  }, []);

  const removeMarker = useCallback((id: string) => {
    if (!markersLayerRef.current) return;
    const feature = markersRef.current.get(id);
    if (feature) {
      markersLayerRef.current.getSource()?.removeFeature(feature);
      markersRef.current.delete(id);
    }
  }, []);

  const clearMarkers = useCallback(() => {
    if (!markersLayerRef.current) return;
    markersLayerRef.current.getSource()?.clear();
    markersRef.current.clear();
  }, []);

  // State export/import
  const exportState = useCallback(() => {
    if (!mapRef.current) return null;
    return {
      center,
      zoom,
      rotation: mapRef.current.view.getRotation(),
      baseLayer: Array.from(mapRef.current.baseLayers.entries()).find(([, l]) => l.getVisible())?.[0],
      overlays: Array.from(mapRef.current.overlayLayers.entries())
        .filter(([, l]) => l.getVisible())
        .map(([id]) => id),
    };
  }, [center, zoom]);

  const importState = useCallback((state: any) => {
    if (!mapRef.current || !state) return;
    animateTo(state.center, state.zoom);
    if (state.baseLayer) setBaseLayer(state.baseLayer);
    mapRef.current.overlayLayers.forEach((layer, id) => {
      layer.setVisible(state.overlays?.includes(id) ?? false);
    });
  }, [animateTo, setBaseLayer]);

  return {
    mapInstance: mapRef.current,
    center,
    zoom,
    resolution,
    animateTo,
    setBaseLayer,
    toggleOverlay,
    setLayerOpacity,
    addMarker,
    removeMarker,
    clearMarkers,
    exportState,
    importState,
  };
}
