import React, { useState, useEffect, useMemo } from 'react'
import RailMap from './map/RailMap'
import Sidebar from './sidebar/Sidebar'
import Filters from './sidebar/Filters'

const layout = {
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
    margin: '0',
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

const COMMIT_HASH = 'bce68229b1a456fae3fae37ddca2886e2a11443c'
const CDN_BASE  = `https://cdn.jsdelivr.net/gh/rodeocrazy/italian-rail-map@${COMMIT_HASH}/public/data`
const LOCAL_BASE = '/data'

async function fetchData(name) {
  const base = import.meta.env.DEV ? LOCAL_BASE : CDN_BASE
  const res = await fetch(`${base}/${name}.json`)
  return res.json()
}

export default function App() {
  const [stations, setStations]   = useState([])
  const [edges, setEdges]         = useState([])
  const [loading, setLoading]     = useState(true)
  const [selected, setSelected]   = useState(null)
  const [highlightLine, setHighlightLine] = useState(null)
  const [search, setSearch]       = useState('')
  const [filters, setFilters]     = useState({
    types:        ['station'],
    hideInactive: false,
  })

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

  // All edges for the selected station's lines
  const visibleEdges = useMemo(() => {
    if (!selected) return []
    const lineIds = new Set(
      edges
        .filter(e => e.station_a_id === selected.id || e.station_b_id === selected.id)
        .map(e => e.line_id)
    )
    return edges.filter(e => lineIds.has(e.line_id))
  }, [selected, edges])

  // Filtered stations — always include stations on the selected line
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

  // Lines connected to selected station (for sidebar)
  const connectedLines = useMemo(() => {
    if (!selected) return []
    const seen = new Set()
    return visibleEdges
      .filter(e =>
        (e.station_a_id === selected.id || e.station_b_id === selected.id) &&
        !seen.has(e.line_id) && seen.add(e.line_id)
      )
      .map(e => ({
        line_id:       e.line_id,
        line_name:     e.line_name,
        route_type:    e.route_type,
        line_operator: e.line_operator,
      }))
  }, [selected, visibleEdges])

  // Stats
  const stats = useMemo(() => {
    const connectedIds = new Set([
      ...edges.map(e => e.station_a_id),
      ...edges.map(e => e.station_b_id),
    ])
    const lineIds = new Set(edges.map(e => e.line_id))
    return {
      total:     stations.length,
      connected: connectedIds.size,
      edges:     edges.length,
      lines:     lineIds.size,
    }
  }, [stations, edges])

  const handleSelectStation = (station) => {
    setSelected(prev => prev?.id === station?.id ? null : station)
    setHighlightLine(null)
  }

  return (
    <div style={layout.root}>
      <div style={layout.panel}>
        <div style={layout.header}>
          <div style={layout.title}>Rete Ferroviaria</div>
          <div style={layout.subtitle}>Italy Rail Network</div>
        </div>

        <div style={layout.search}>
          <input
            style={layout.searchInput}
            placeholder="Search stations..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            onFocus={e => e.target.style.borderColor = '#2a3f55'}
            onBlur={e => e.target.style.borderColor = '#1e2d3d'}
          />
        </div>

        <div style={layout.filtersScroll}>
          <Filters filters={filters} onChange={setFilters} stats={stats} />
        </div>

        <div style={layout.divider} />

        <Sidebar
          station={selected}
          connectedLines={connectedLines}
          onHighlightLine={setHighlightLine}
        />
      </div>

      <div style={layout.mapContainer}>
        {loading && (
          <div style={layout.loadingOverlay}>
            loading network data...
          </div>
        )}
        {!loading && (
          <RailMap
            stations={visibleStations}
            edges={visibleEdges}
            selectedStation={selected}
            highlightLineId={highlightLine}
            onSelectStation={handleSelectStation}
          />
        )}
      </div>
    </div>
  )
}