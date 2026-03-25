import React, { useState, useEffect, useMemo } from 'react'
import RailMap from './map/RailMap'
import Sidebar from './sidebar/Sidebar'
import Filters from './sidebar/Filters'

const COMMIT_HASH = '04300228d5108558ff2ef63e979659398c47d5d6'
const CDN_BASE   = `https://cdn.jsdelivr.net/gh/rodeocrazy/italian-rail-map@${COMMIT_HASH}/public/data`
const LOCAL_BASE = '/data'

async function fetchData(name) {
  const base = import.meta.env.DEV ? LOCAL_BASE : CDN_BASE
  const res = await fetch(`${base}/${name}.json`)
  return res.json()
}

function useIsMobile() {
  const [isMobile, setIsMobile] = useState(() => window.innerWidth < 768)
  useEffect(() => {
    const handler = () => setIsMobile(window.innerWidth < 768)
    window.addEventListener('resize', handler)
    return () => window.removeEventListener('resize', handler)
  }, [])
  return isMobile
}

const desktop = {
  root: {
    display: 'flex',
    width: '100vw',
    height: '100vh',
    background: '#080c10',
    overflow: 'hidden',
  },
  panel: {
    width: '260px',
    minWidth: '260px',
    height: '100%',
    display: 'flex',
    flexDirection: 'column',
    background: '#0d1117',
    borderRight: '1px solid #1e2d3d',
    zIndex: 10,
    overflow: 'hidden',
  },
  header: {
    padding: '18px 16px 14px',
    borderBottom: '1px solid #1e2d3d',
    flexShrink: 0,
  },
  title: {
    fontFamily: "'Bebas Neue', sans-serif",
    fontSize: '20px',
    letterSpacing: '0.1em',
    color: '#00d4ff',
    lineHeight: 1,
    marginBottom: '2px',
  },
  subtitle: {
    fontFamily: "'DM Mono', monospace",
    fontSize: '10px',
    color: '#3d5266',
    letterSpacing: '0.1em',
    textTransform: 'uppercase',
  },
  search: {
    padding: '10px 16px',
    borderBottom: '1px solid #1e2d3d',
    flexShrink: 0,
  },
  searchInput: {
    width: '100%',
    background: '#141b24',
    border: '1px solid #1e2d3d',
    borderRadius: '2px',
    padding: '7px 10px',
    color: '#c8d8e8',
    fontFamily: "'DM Mono', monospace",
    fontSize: '12px',
    outline: 'none',
    transition: 'border-color 0.15s',
  },
  filtersScroll: {
    overflowY: 'auto',
    flexShrink: 0,
  },
  divider: {
    height: '1px',
    background: '#1e2d3d',
  },
  mapContainer: {
    flex: 1,
    position: 'relative',
    overflow: 'hidden',
  },
  loadingOverlay: {
    position: 'absolute',
    inset: 0,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: '#080c10',
    zIndex: 20,
    fontFamily: "'DM Mono', monospace",
    fontSize: '12px',
    color: '#3d5266',
    letterSpacing: '0.1em',
  },
}

export default function App() {
  const isMobile = useIsMobile()

  const [stations, setStations]           = useState([])
  const [edges, setEdges]                 = useState([])
  const [loading, setLoading]             = useState(true)
  const [selected, setSelected]           = useState(null)
  const [highlightLine, setHighlightLine] = useState(null)
  const [search, setSearch]               = useState('')
  const [filters, setFilters]             = useState({ types: ['station'], hideInactive: false })
  const [showFilters, setShowFilters]     = useState(false)

  useEffect(() => {
    Promise.all([
      fetchData('stations'),
      fetchData('edges'),
    ]).then(([s, e]) => {
      setStations(s)
      setEdges(e)
      setLoading(false)
    })
  }, [])

  const visibleEdges = useMemo(() => {
    if (!selected) return []
    const lineIds = new Set(
      edges
        .filter(e => e.station_a_id === selected.id || e.station_b_id === selected.id)
        .map(e => e.line_id)
    )
    return edges.filter(e => lineIds.has(e.line_id))
  }, [selected, edges])

  const visibleStations = useMemo(() => {
    const edgeStationIds = new Set([
      ...visibleEdges.map(e => e.station_a_id),
      ...visibleEdges.map(e => e.station_b_id),
    ])
    return stations.filter(s => {
      if (edgeStationIds.has(s.id)) return true
      if (filters.hideInactive && s.active === 0) return false
      const effectiveType = s.station || s.railway
      if (filters.types.length && !filters.types.includes(effectiveType)) return false
      if (search.trim()) {
        const q = search.toLowerCase()
        return (
          s.name?.toLowerCase().includes(q) ||
          s.official_name?.toLowerCase().includes(q) ||
          s.addr_city?.toLowerCase().includes(q)
        )
      }
      return true
    })
  }, [stations, filters, search, visibleEdges])

  const connectedLines = useMemo(() => {
    if (!selected) return []
    const seen = new Set()
    return visibleEdges
      .filter(e =>
        (e.station_a_id === selected.id || e.station_b_id === selected.id) &&
        !seen.has(e.line_name) && seen.add(e.line_name)
      )
      .map(e => ({
        line_id:       e.line_id,
        line_name:     e.line_name,
        route_type:    e.route_type,
        line_operator: e.line_operator,
      }))
  }, [selected, visibleEdges])

  const stats = useMemo(() => {
    const connectedIds = new Set([
      ...edges.map(e => e.station_a_id),
      ...edges.map(e => e.station_b_id),
    ])
    return {
      total:     stations.length,
      connected: connectedIds.size,
      edges:     edges.length,
      lines:     new Set(edges.map(e => e.line_id)).size,
    }
  }, [stations, edges])

  const handleSelectStation = (station) => {
    setSelected(prev => prev?.id === station?.id ? null : station)
    setHighlightLine(null)
  }

  const handleDeselect = () => {
    setSelected(null)
    setHighlightLine(null)
  }

  // ── Mobile layout ──────────────────────────────────────────────────────────
  if (isMobile) {
    return (
      <div style={{
        width: '100vw',
        height: '100vh',
        background: '#080c10',
        position: 'relative',
        overflow: 'hidden',
      }}>

        {/* Full screen map */}
        <div style={{ position: 'absolute', inset: 0 }}>
          {loading && (
            <div style={desktop.loadingOverlay}>loading network data...</div>
          )}
          {!loading && (
            <RailMap
              stations={visibleStations}
              edges={visibleEdges}
              selectedStation={selected}
              highlightLineId={highlightLine}
              onSelectStation={handleSelectStation}
              onDeselectStation={handleDeselect}
            />
          )}
        </div>

        {/* Top bar */}
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0,
          display: 'flex', alignItems: 'center', gap: '8px',
          padding: '10px 12px',
          background: 'rgba(13,17,23,0.92)',
          borderBottom: '1px solid #1e2d3d',
          backdropFilter: 'blur(8px)',
          zIndex: 20,
        }}>
          <div style={{
            fontFamily: "'Bebas Neue', sans-serif",
            fontSize: '18px',
            color: '#00d4ff',
            letterSpacing: '0.1em',
            flexShrink: 0,
          }}>
            Mappa Ferroviaria Unificata
          </div>
          <input
            style={{
              flex: 1,
              minWidth: 0,
              background: '#141b24',
              border: '1px solid #1e2d3d',
              borderRadius: '2px',
              padding: '5px 8px',
              color: '#c8d8e8',
              fontFamily: "'DM Mono', monospace",
              fontSize: '11px',
              outline: 'none',
            }}
            placeholder="Search..."
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
          <button
            onClick={() => setShowFilters(true)}
            style={{
              background: '#141b24',
              border: '1px solid #1e2d3d',
              borderRadius: '2px',
              color: '#6b8299',
              fontFamily: "'DM Mono', monospace",
              fontSize: '11px',
              padding: '6px 10px',
              cursor: 'pointer',
              flexShrink: 0,
            }}
          >
            Filter
          </button>
        </div>

        {/* Bottom sheet */}
        <div style={{
          position: 'absolute', bottom: 0, left: 0, right: 0,
          background: '#0d1117',
          borderTop: '1px solid #1e2d3d',
          borderRadius: '12px 12px 0 0',
          zIndex: 20,
          maxHeight: selected ? '55vh' : '0',
          overflow: 'hidden',
          transition: 'max-height 0.3s ease',
        }}>
          <div style={{ display: 'flex', justifyContent: 'center', padding: '10px 0 4px' }}>
            <div style={{ width: '36px', height: '4px', borderRadius: '2px', background: '#1e2d3d' }} />
          </div>
          <div style={{ overflowY: 'auto', maxHeight: 'calc(55vh - 24px)' }}>
            <Sidebar
              station={selected}
              connectedLines={connectedLines}
              onHighlightLine={setHighlightLine}
            />
          </div>
        </div>

        {/* Filter modal */}
        {showFilters && (
          <div
            style={{
              position: 'absolute', inset: 0, zIndex: 30,
              background: 'rgba(8,12,16,0.85)',
              backdropFilter: 'blur(4px)',
              display: 'flex', alignItems: 'flex-end',
            }}
            onClick={() => setShowFilters(false)}
          >
            <div
              style={{
                width: '100%',
                background: '#0d1117',
                borderTop: '1px solid #1e2d3d',
                borderRadius: '12px 12px 0 0',
                padding: '16px 0',
              }}
              onClick={e => e.stopPropagation()}
            >
              <div style={{
                fontFamily: "'DM Mono', monospace",
                fontSize: '10px',
                color: '#3d5266',
                letterSpacing: '0.12em',
                textTransform: 'uppercase',
                padding: '0 16px 12px',
                borderBottom: '1px solid #1e2d3d',
                marginBottom: '4px',
              }}>
                Filters
              </div>
              <Filters filters={filters} onChange={setFilters} stats={stats} />
              <div style={{ padding: '12px 16px 0' }}>
                <button
                  onClick={() => setShowFilters(false)}
                  style={{
                    width: '100%',
                    background: 'rgba(0,212,255,0.1)',
                    border: '1px solid #00d4ff40',
                    borderRadius: '2px',
                    color: '#00d4ff',
                    fontFamily: "'DM Mono', monospace",
                    fontSize: '12px',
                    padding: '10px',
                    cursor: 'pointer',
                  }}
                >
                  Done
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    )
  }

  // ── Desktop layout ─────────────────────────────────────────────────────────
  return (
    <div style={desktop.root}>
      <div style={desktop.panel}>
        <div style={desktop.header}>
          <div style={desktop.title}>Mappa Ferroviaria Unificata</div>
          <div style={desktop.subtitle}>Unified Italian Rail Map</div>
        </div>
        <div style={desktop.search}>
          <input
            style={desktop.searchInput}
            placeholder="Search stations..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            onFocus={e => e.target.style.borderColor = '#2a3f55'}
            onBlur={e => e.target.style.borderColor = '#1e2d3d'}
          />
        </div>
        <div style={desktop.filtersScroll}>
          <Filters filters={filters} onChange={setFilters} stats={stats} />
        </div>
        <div style={desktop.divider} />
        <Sidebar
          station={selected}
          connectedLines={connectedLines}
          onHighlightLine={setHighlightLine}
        />
      </div>
      <div style={desktop.mapContainer}>
        {loading && (
          <div style={desktop.loadingOverlay}>loading network data...</div>
        )}
        {!loading && (
          <RailMap
            stations={visibleStations}
            edges={visibleEdges}
            selectedStation={selected}
            highlightLineId={highlightLine}
            onSelectStation={handleSelectStation}
            onDeselectStation={handleDeselect}
          />
        )}
      </div>
    </div>
  )
}