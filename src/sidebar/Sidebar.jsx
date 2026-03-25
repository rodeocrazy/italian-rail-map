import React from 'react'

const s = {
  container: {
    flex: 1,
    overflowY: 'auto',
    padding: '16px',
  },
  empty: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    height: '100%',
    color: '#3d5266',
    fontFamily: "'DM Mono', monospace",
    fontSize: '11px',
    textAlign: 'center',
    gap: '8px',
    padding: '32px 16px',
  },
  name: {
    fontFamily: "'Bebas Neue', sans-serif",
    fontSize: '22px',
    letterSpacing: '0.05em',
    color: '#c8d8e8',
    lineHeight: 1.1,
    marginBottom: '4px',
  },
  official: {
    fontFamily: "'DM Mono', monospace",
    fontSize: '10px',
    color: '#3d5266',
    marginBottom: '16px',
    letterSpacing: '0.05em',
  },
  divider: {
    height: '1px',
    background: '#1e2d3d',
    margin: '14px 0',
  },
  row: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'baseline',
    marginBottom: '8px',
  },
  rowLabel: {
    fontFamily: "'DM Mono', monospace",
    fontSize: '10px',
    color: '#3d5266',
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
  },
  rowValue: {
    fontFamily: "'DM Mono', monospace",
    fontSize: '12px',
    color: '#c8d8e8',
    textAlign: 'right',
    maxWidth: '130px',
  },
  badge: (active) => ({
    display: 'inline-block',
    padding: '2px 8px',
    borderRadius: '2px',
    fontSize: '10px',
    fontFamily: "'DM Mono', monospace",
    background: active ? 'rgba(0,212,255,0.1)' : 'rgba(100,100,100,0.1)',
    border: `1px solid ${active ? '#00d4ff40' : '#2a3f55'}`,
    color: active ? '#00d4ff' : '#3d5266',
    letterSpacing: '0.08em',
  }),
  sectionLabel: {
    fontFamily: "'DM Mono', monospace",
    fontSize: '10px',
    color: '#3d5266',
    textTransform: 'uppercase',
    letterSpacing: '0.12em',
    marginBottom: '10px',
  },
  lineItem: {
    padding: '8px 10px',
    background: '#141b24',
    border: '1px solid #1e2d3d',
    borderRadius: '2px',
    marginBottom: '6px',
    cursor: 'pointer',
    transition: 'border-color 0.15s',
  },
  lineName: {
    fontFamily: "'DM Mono', monospace",
    fontSize: '11px',
    color: '#c8d8e8',
    marginBottom: '2px',
  },
  lineMeta: {
    fontFamily: "'DM Mono', monospace",
    fontSize: '10px',
    color: '#3d5266',
  },
  coords: {
    fontFamily: "'DM Mono', monospace",
    fontSize: '10px',
    color: '#3d5266',
    marginTop: '14px',
  },
  externalLinks: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
    marginTop: '10px',
  },
  link: {
    fontFamily: "'DM Mono', monospace",
    fontSize: '10px',
    color: '#00d4ff',
    textDecoration: 'none',
    letterSpacing: '0.05em',
  },
}

function Row({ label, value }) {
  if (!value && value !== 0) return null
  return (
    <div style={s.row}>
      <span style={s.rowLabel}>{label}</span>
      <span style={s.rowValue}>{value}</span>
    </div>
  )
}

function buildWikiUrl(wikipedia) {
  if (!wikipedia) return null
  const match = wikipedia.match(/^([a-z]+):(.+)$/)
  if (match) {
    const [, lang, title] = match
    return `https://${lang}.wikipedia.org/wiki/${encodeURIComponent(title.replace(/ /g, '_'))}`
  }
  return `https://en.wikipedia.org/wiki/${encodeURIComponent(wikipedia.replace(/ /g, '_'))}`
}

export default function Sidebar({ station, connectedLines, onHighlightLine }) {
  if (!station) {
    return (
      <div style={s.container}>
        <div style={s.empty}>
          <div style={{ fontSize: '24px', opacity: 0.3 }}>◎</div>
          <div>Select a station<br />to view details</div>
        </div>
      </div>
    )
  }

  const wikiUrl = buildWikiUrl(station.wikipedia)
  const googleMapsUrl = `https://www.google.com/maps/search/${encodeURIComponent(station.name)}/@${station.lat},${station.lon},15z`

  return (
    <div style={s.container}>
      <div style={s.name}>{station.name}</div>
      {station.official_name && station.official_name !== station.name && (
        <div style={s.official}>{station.official_name}</div>
      )}

      <span style={s.badge(station.active !== 0)}>
        {station.active !== 0 ? 'active' : 'disused'}
      </span>

      <div style={s.divider} />

      <Row label="Type"       value={station.railway} />
      <Row label="Operator"   value={station.operator} />
      <Row label="Category"   value={station.station_category} />
      <Row label="UIC ref"    value={station.uic_ref} />
      <Row label="Platforms"  value={station.platforms} />
      <Row label="Wheelchair" value={station.wheelchair} />
      <Row label="Elevation"  value={station.ele ? `${station.ele}m` : null} />
      <Row label="City"       value={station.addr_city} />

      <div style={s.coords}>
        {station.lat.toFixed(5)}, {station.lon.toFixed(5)}
      </div>

      <div style={s.externalLinks}>
        {wikiUrl && (
          <a href={wikiUrl} target="_blank" rel="noreferrer" style={s.link}>
            → Wikipedia
          </a>
        )}
        <a href={googleMapsUrl} target="_blank" rel="noreferrer" style={s.link}>
          → Google Maps
        </a>
      </div>

      {connectedLines.length > 0 && (
        <>
          <div style={s.divider} />
          <div style={s.sectionLabel}>Connected lines ({connectedLines.length})</div>
          {connectedLines.map(line => (
            <div
              key={line.osm_relation_id || line.line_id}
              style={s.lineItem}
              onClick={() => onHighlightLine(line.line_id)}
              onMouseEnter={e => e.currentTarget.style.borderColor = '#2a3f55'}
              onMouseLeave={e => e.currentTarget.style.borderColor = '#1e2d3d'}
            >
              <div style={s.lineName}>{line.line_name || 'Unnamed line'}</div>
              <div style={s.lineMeta}>
                {[line.route_type, line.line_operator].filter(Boolean).join(' · ')}
              </div>
            </div>
          ))}
        </>
      )}
    </div>
  )
}