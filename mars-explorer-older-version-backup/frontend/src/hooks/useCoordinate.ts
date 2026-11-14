/** MARS EXPLORER - Coordinate Formatting Hook */
import { useMemo, useCallback } from 'react';
import type { Coordinate } from '../types';
import { formatDMS, formatDD, parseCoordinate } from '../services/marsMapService';

export interface UseCoordinateReturn {
  formatDMS: (coord: Coordinate) => string;
  formatDD: (coord: Coordinate, precision?: number) => string;
  formatShort: (coord: Coordinate) => string;
  parse: (input: string) => Coordinate | null;
  validate: (coord: Coordinate) => boolean;
  normalize: (coord: Coordinate) => Coordinate;
}

export function useCoordinate(): UseCoordinateReturn {
  const formatDMSFn = useCallback((coord: Coordinate): string => {
    return formatDMS(coord.longitude, coord.latitude);
  }, []);

  const formatDDFn = useCallback((coord: Coordinate, precision = 6): string => {
    return formatDD(coord.longitude, coord.latitude, precision);
  }, []);

  const formatShort = useCallback((coord: Coordinate): string => {
    return `${coord.latitude.toFixed(4)}°, ${coord.longitude.toFixed(4)}°`;
  }, []);

  const parse = useCallback((input: string): Coordinate | null => {
    return parseCoordinate(input);
  }, []);

  const validate = useCallback((coord: Coordinate): boolean => {
    return (
      typeof coord.longitude === 'number' &&
      typeof coord.latitude === 'number' &&
      coord.longitude >= -180 &&
      coord.longitude <= 180 &&
      coord.latitude >= -90 &&
      coord.latitude <= 90 &&
      !isNaN(coord.longitude) &&
      !isNaN(coord.latitude)
    );
  }, []);

  const normalize = useCallback((coord: Coordinate): Coordinate => {
    let lon = coord.longitude;
    let lat = coord.latitude;
    
    // Normalize longitude to -180..180
    lon = ((lon + 180) % 360) - 180;
    
    // Clamp latitude
    lat = Math.max(-90, Math.min(90, lat));
    
    return { longitude: lon, latitude: lat };
  }, []);

  return {
    formatDMS: formatDMSFn,
    formatDD: formatDDFn,
    formatShort,
    parse,
    validate,
    normalize,
  };
}
