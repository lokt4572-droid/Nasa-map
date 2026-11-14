/** MARS EXPLORER - Dataset Service */
import { api } from './api';
import type { Dataset, DatasetLayer, NasaLayerMeta } from '../types';
import { NASA_LAYERS } from '../config/mapLayers';

export interface DatasetWithLayers extends Dataset {
  layers: DatasetLayer[];
}

class DatasetService {
  private cache: Map<string, DatasetWithLayers> = new Map();
  private nasaLayersCache: NasaLayerMeta[] | null = null;

  // NASA Mars Trek layers (static config)
  getNasaLayers(): NasaLayerMeta[] {
    if (this.nasaLayersCache) return this.nasaLayersCache;
    this.nasaLayersCache = NASA_LAYERS;
    return this.nasaLayersCache;
  }

  getNasaLayerByKey(key: string): NasaLayerMeta | undefined {
    return NASA_LAYERS.find(l => l.key === key);
  }

  getBaseLayers(): NasaLayerMeta[] {
    return NASA_LAYERS.filter(l => l.type === 'hillshade' || l.type === 'orthoimage');
  }

  getOverlayLayers(): NasaLayerMeta[] {
    return NASA_LAYERS.filter(l => l.type !== 'hillshade' && l.type !== 'orthoimage');
  }

  // Database datasets
  async fetchDatasets(params?: Record<string, string>): Promise<Dataset[]> {
    const response = await api.datasets.list(params);
    return response.results;
  }

  async fetchDataset(id: string): Promise<DatasetWithLayers | null> {
    if (this.cache.has(id)) {
      return this.cache.get(id)!;
    }

    try {
      const dataset = await api.datasets.get(id);
      const layersResponse = await api.datasets.layers.list({ dataset: id });
      const result: DatasetWithLayers = { ...dataset, layers: layersResponse.results };
      this.cache.set(id, result);
      return result;
    } catch {
      return null;
    }
  }

  async fetchLayers(params?: Record<string, string>): Promise<DatasetLayer[]> {
    const response = await api.datasets.layers.list(params);
    return response.results;
  }

  // Combine NASA + DB layers for map
  async getAllMapLayers(): Promise<DatasetLayer[]> {
    const nasaLayers = this.getNasaLayers().map(meta => ({
      id: `nasa_${meta.key}`,
      name: meta.name,
      type: 'wmts' as const,
      datasetId: 'nasa_trek',
      urlTemplate: meta.wmtsUrl,
      wmtsLayerId: meta.identifier,
      wmtsMatrixSet: 'Mars_Equirectangular',
      wmtsStyle: meta.wmtsStyle,
      wmtsFormat: meta.wmtsFormat,
      attribution: meta.attribution,
      opacity: meta.type === 'hillshade' ? 1.0 : 0.8,
      isBaseLayer: meta.type === 'hillshade' || meta.type === 'orthoimage',
      isVisible: meta.type === 'hillshade',
      zIndex: meta.type === 'hillshade' ? 10 : 20,
      minZoom: 0,
      maxZoom: 18,
    }));

    const dbLayers = await this.fetchLayers({ is_visible: 'true' });
    
    return [...nasaLayers, ...dbLayers];
  }

  // Clear cache
  clearCache(): void {
    this.cache.clear();
  }

  invalidateDataset(id: string): void {
    this.cache.delete(id);
  }
}

export const datasetService = new DatasetService();
