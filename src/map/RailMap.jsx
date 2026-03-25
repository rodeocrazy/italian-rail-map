import React, { useState, useEffect, useCallback, useMemo } from 'react'
import Map from 'react-map-gl'
import DeckGL from '@deck.gl/react'
import { buildStationLayer, buildEdgeLayer } from './layers'
import 'mapbox-gl/dist/mapbox-gl.css'

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN

const INITIAL_VIEW = {
  longitude: 12.5,
  latitude:  42.0,
  zoom:      5.5,
  pitch:     0,
  bearing:   0,
}

const tooltipStyle = {
  position:       'absolute',
  pointerEvents:  'none',
  background:     'rgba(13,17,23,0.95)',
  border:         '1px solid #1e2d3d',
  borderLeft:     '2px solid #ffc850',
  color:          '#c8d8e8',
  fontFamily:     "'DM Mono', monospace",
  fontSize:       '11px',
  padding:        '8px 12px',
  borderRadius:   '2px',
  maxWidth:       '220px',
  lineHeight:     '1.6',
  backdropFilter: 'blur(4px)',
}

export default function RailMap({
  stations,
  edges,
  selectedStation,
  highlightLineId,
  onSelectStation,
}) {
  const [hoverInfo, setHoverInfo] = useState(null)
  const [viewState, setViewState] = useState(INITIAL_VIEW)
  const [mounted, setMounted]     = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  const handleHover = useCallback(({ object, x, y }) => {
    setHoverInfo(object ? { object, x, y } : null)
  }, [])

  const hasSelection = !!selectedStation

  // Build set of station IDs that are on the selected line
  const lineStationIds = useMemo(() => {
    if (!hasSelection) return new Set()
    return new Set([
      ...edges.map(e => e.station_a_id),
      ...edges.map(e => e.station_b_id),
    ])
  }, [edges, hasSelection])

  const layers = [
    buildEdgeLayer({ edges, highlightLineId }),
    buildStationLayer({
      stations,
      selectedId:     selectedStation?.id,
      hasSelection,
      lineStationIds,
      onHover:        handleHover,
      onClick:        onSelectStation,
    }),
  ]

  if (!mounted) return null

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <DeckGL
        viewState={viewState}
        onViewStateChange={({ viewState }) => setViewState(viewState)}
        controller={true}
        layers={layers}
      >
        <Map
          mapboxAccessToken={MAPBOX_TOKEN}
          mapStyle="mapbox://styles/mapbox/dark-v11"
          reuseMaps
        />
      </DeckGL>

      {hoverInfo && (
        <div style={{ ...tooltipStyle, left: hoverInfo.x + 12, top: hoverInfo.y - 10 }}>
          <div style={{ color: '#ffc850', fontWeight: 500, marginBottom: 4 }}>
            {hoverInfo.object.name || 'Unnamed'}
          </div>
          {hoverInfo.object.operator && (
            <div style={{ color: '#6b8299' }}>{hoverInfo.object.operator}</div>
          )}
          <div style={{ color: '#3d5266', marginTop: 2 }}>
            {hoverInfo.object.railway}
            {hoverInfo.object.active === 0 && ' · disused'}
          </div>
        </div>
      )}
    </div>
  )
}