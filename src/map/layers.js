import { ScatterplotLayer, LineLayer } from '@deck.gl/layers'

const RAILWAY_COLORS = {
  station: [0, 212, 255],
  halt:    [255, 107, 53],
  default: [100, 150, 200],
}

const INACTIVE_COLOR = [42, 63, 85]
const DIMMED_COLOR   = [30, 45, 60, 80]
const GOLD           = [255, 200, 80, 255]
const GOLD_BRIGHT    = [255, 215, 100, 255]

export function buildStationLayer({ stations, selectedId, hasSelection, lineStationIds, onHover, onClick }) {
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
      if (d.id === selectedId) return [255, 255, 255]
      // Keep line stations lit, dim everything else
      if (hasSelection) {
        if (lineStationIds.has(d.id)) return RAILWAY_COLORS[d.railway] || RAILWAY_COLORS.default
        return DIMMED_COLOR
      }
      if (d.active === 0) return INACTIVE_COLOR
      return RAILWAY_COLORS[d.railway] || RAILWAY_COLORS.default
    },

    getLineColor: d => {
      if (d.id === selectedId) return [255, 200, 80]
      if (hasSelection && lineStationIds.has(d.id)) return [0, 0, 0, 40]
      return [0, 0, 0, 40]
    },

    getLineWidth: d => d.id === selectedId ? 2 : 1,

    onHover,
    onClick: ({ object }) => onClick(object),
    updateTriggers: {
      getFillColor: [selectedId, hasSelection, lineStationIds],
      getRadius:    [selectedId],
      getLineColor: [selectedId, hasSelection],
      getLineWidth: [selectedId],
    },
  })
}

export function buildEdgeLayer({ edges, highlightLineId }) {
  return new LineLayer({
    id: 'edges',
    data: edges,
    pickable: false,
    getWidth: 2.5,
    getColor: d => {
      if (d.line_id === highlightLineId) return GOLD_BRIGHT
      return GOLD
    },
    getSourcePosition: d => [d.lon_a, d.lat_a],
    getTargetPosition: d => [d.lon_b, d.lat_b],
    updateTriggers: {
      getColor: [highlightLineId],
    },
  })
}