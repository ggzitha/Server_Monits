import { describe, it, expect } from 'vitest';
import { snap, formatMeters, parseMeters, calculatePolygonArea, calculateDistance2D } from '../src/core/units.ts';

describe('Metric Units & Snapping', () => {
  it('should snap values to 0.05m step', () => {
    expect(snap(1.23, 0.05)).toBe(1.25);
    expect(snap(1.22, 0.05)).toBe(1.20);
    expect(snap(0.04, 0.05)).toBe(0.05);
  });

  it('should snap values to 0.1m step', () => {
    expect(snap(2.34, 0.1)).toBe(2.3);
    expect(snap(2.36, 0.1)).toBe(2.4);
  });

  it('should snap values to 0.5m step', () => {
    expect(snap(1.2, 0.5)).toBe(1.0);
    expect(snap(1.3, 0.5)).toBe(1.5);
    expect(snap(3.8, 0.5)).toBe(4.0);
  });

  it('should format meters correctly', () => {
    expect(formatMeters(2.5)).toBe('2.50 m');
    expect(formatMeters(10.123, 1)).toBe('10.1 m');
  });

  it('should parse meter strings cleanly', () => {
    expect(parseMeters('12.5m')).toBe(12.5);
    expect(parseMeters('4.80 meters')).toBe(4.8);
    expect(parseMeters('invalid', 1.0)).toBe(1.0);
  });

  it('should calculate 2D Euclidean distance in meters', () => {
    const dist = calculateDistance2D([0, 0], [3, 4]);
    expect(dist).toBe(5.0);
  });

  it('should calculate closed polygon area in square meters', () => {
    // 10m x 8m rectangle
    const rect: [number, number][] = [
      [0, 0],
      [10, 0],
      [10, 8],
      [0, 8]
    ];
    expect(calculatePolygonArea(rect)).toBe(80.0);
  });
});

