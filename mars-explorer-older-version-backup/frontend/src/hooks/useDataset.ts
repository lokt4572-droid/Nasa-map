/** MARS EXPLORER - Dataset Hook */
import { useState, useEffect, useCallback } from 'react';
import { datasetService } from '../services/datasetService';
import type { Dataset, DatasetLayer, NasaLayerMeta } from '../types';

export function useDatasets() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchDatasets = useCallback(async (params?: Record<string, string>) => {
    setLoading(true);
    setError(null);
    try {
      const data = await datasetService.fetchDatasets(params);
      setDatasets(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch datasets');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDatasets();
  }, [fetchDatasets]);

  return { datasets, loading, error, refetch: fetchDatasets };
}

export function useNasaLayers() {
  const [layers, setLayers] = useState<NasaLayerMeta[]>([]);
  
  useEffect(() => {
    setLayers(datasetService.getNasaLayers());
  }, []);

  const getBaseLayers = useCallback(() => datasetService.getBaseLayers(), []);
  const getOverlayLayers = useCallback(() => datasetService.getOverlayLayers(), []);
  const getLayerByKey = useCallback((key: string) => datasetService.getNasaLayerByKey(key), []);

  return { layers, getBaseLayers, getOverlayLayers, getLayerByKey };
}

export function useDataset(id: string | null) {
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchDataset = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const data = await datasetService.fetchDataset(id);
      setDataset(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch dataset');
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchDataset();
  }, [fetchDataset]);

  return { dataset, loading, error, refetch: fetchDataset };
}
