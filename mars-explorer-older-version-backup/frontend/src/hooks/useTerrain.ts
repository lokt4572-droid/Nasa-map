/** MARS EXPLORER - Terrain Analysis Hook */
import { useState, useCallback } from 'react';
import { api } from '../services/api';
import type { ElevationProfile, TerrainAnalysis } from '../types';

export function useTerrain() {
  const [profile, setProfile] = useState<ElevationProfile | null>(null);
  const [analyses, setAnalyses] = useState<TerrainAnalysis[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const getProfile = useCallback(async (coordinates: Array<{ longitude: number; latitude: number }>, demSource?: string) => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.terrain.profile({ coordinates, dem_source: demSource });
      setProfile(result);
      return result;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to get elevation profile');
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const createAnalysis = useCallback(async (data: Partial<TerrainAnalysis>) => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.terrain.create(data);
      setAnalyses(prev => [result, ...prev]);
      return result;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create analysis');
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchAnalyses = useCallback(async (params?: Record<string, string>) => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.terrain.list(params);
      setAnalyses(response.results);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch analyses');
    } finally {
      setLoading(false);
    }
  }, []);

  return {
    profile,
    analyses,
    loading,
    error,
    getProfile,
    createAnalysis,
    fetchAnalyses,
    clearProfile: () => setProfile(null),
  };
}
