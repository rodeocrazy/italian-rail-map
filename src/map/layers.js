import { ScatterplotLayer, LineLayer } from '@deck.gl/layers'

const RAILWAY_COLORS = {
  station:    [0, 212, 255],
  halt:       [255, 107, 53],
  tram_stop:  [255, 200, 0],
  default:    [100, 150, 200],
}

const INACTIVE_COLOR = [42, 63, 85]

export function buildStationLayer({ stations, selectedId, onHover, onClick }) {
  return new ScatterplotLayer({
    id: 'stations',
    data: stations,
    pickable: true,
    opacity: 1,
    stroked: true,
    filled: true,
    radiusScale: 1,
    radiusMinPixels: 3,
    radiusMaxPixels: 10,
    lineWidthMinPixels: 1,

    getPosition: d => [d.lon, d.lat],
    getRadius: d => {
      if (d.id === selectedId) return 8
      if (d.railway === 'station') return 5
      return 3
    },
    getFillColor: d => {
      if (d.active === 0) return INACTIVE_COLOR
      const base = RAILWAY_COLORS[d.railway] || RAILWAY_COLORS.default
      if (d.id === selectedId) return [255, 255, 255]
      return base
    },
    getLineColor: d => {
      if (d.id === selectedId) return [0, 212, 255]
      return [0, 0, 0, 80]
    },
    getLineWidth: d => d.id === selectedId ? 2 : 1,

    onHover,
    onClick: ({ object }) => onClick(object),
    updateTriggers: {
      getFillColor: [selectedId],
      getRadius: [selectedId],
      getLineColor: [selectedId],
      getLineWidth: [selectedId],
    },
  })
}

export function buildEdgeLayer({ edges, highlightLineId }) {
  return new LineLayer({
    id: 'edges',
    data: edges,
    pickable: false,
    getWidth: d => d.line_id === highlightLineId ? 2.5 : 1,
    getColor: d => {
      if (d.line_id === highlightLineId) return [0, 212, 255, 220]
      return [0, 180, 220, 80]
    },
    getSourcePosition: d => [d.lon_a, d.lat_a],
    getTargetPosition: d => [d.lon_b, d.lat_b],
    updateTriggers: {
      getColor: [highlightLineId],
      getWidth: [highlightLineId],
    },
  })
}
