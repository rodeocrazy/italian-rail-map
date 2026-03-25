import React from 'react'

const styles = {
  section: {
    borderBottom: '1px solid #1e2d3d',
    padding: '14px 16px',
  },
  label: {
    fontFamily: "'DM Mono', monospace",
    fontSize: '10px',
    letterSpacing: '0.12em',
    color: '#3d5266',
    textTransform: 'uppercase',
    marginBottom: '10px',
  },
  chipRow: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '6px',
  },
  chip: (active) => ({
    padding: '3px 10px',
    borderRadius: '2px',
    fontSize: '11px',
    fontFamily: "'DM Mono', monospace",
    cursor: 'pointer',
    background: active ? 'rgba(0,212,255,0.15)' : '#0d1117',
    border: `1px solid ${active ? '#00d4ff' : '#1e2d3d'}`,
    color: active ? '#00d4ff' : '#6b8299',
    transition: 'all 0.15s ease',
    userSelect: 'none',
  }),
  statRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'baseline',
    marginBottom: '6px',
  },
  statLabel: {
    fontFamily: "'DM Mono', monospace",
    fontSize: '11px',
    color: '#6b8299',
  },
  statValue: {
    fontFamily: "'DM Mono', monospace",
    fontSize: '13px',
    color: '#00d4ff',
  },
}

const TYPES = ['station', 'funicular','subway','halt']

export default function Filters({ filters, onChange, stats }) {
  const toggle = (value) => {
    const current = filters.types || []
    const next = current.includes(value)
      ? current.filter(v => v !== value)
      : [...current, value]
    onChange({ ...filters, types: next })
  }

  const toggleActive = () => {
    onChange({ ...filters, hideInactive: !filters.hideInactive })
  }

  const activeTypes = filters.types || []

  return (
    <>
      {/* Stats */}
      <div style={styles.section}>
        <div style={styles.label}>Network</div>
        <div style={styles.statRow}>
          <span style={styles.statLabel}>Stations</span>
          <span style={styles.statValue}>{stats.total.toLocaleString()}</span>
        </div>
        <div style={styles.statRow}>
          <span style={styles.statLabel}>Connected</span>
          <span style={styles.statValue}>{stats.connected.toLocaleString()}</span>
        </div>
        <div style={styles.statRow}>
          <span style={styles.statLabel}>Edges</span>
          <span style={styles.statValue}>{stats.edges.toLocaleString()}</span>
        </div>
        <div style={styles.statRow}>
          <span style={styles.statLabel}>Lines</span>
          <span style={styles.statValue}>{stats.lines.toLocaleString()}</span>
        </div>
      </div>

      {/* Type filters */}
      <div style={styles.section}>
        <div style={styles.label}>Type</div>
        <div style={styles.chipRow}>
          {TYPES.map(t => (
            <div
              key={t}
              style={styles.chip(activeTypes.includes(t))}
              onClick={() => toggle(t)}
            >
              {t}
            </div>
          ))}
        </div>
      </div>

      {/* Status filter */}
      <div style={styles.section}>
        <div style={styles.label}>Status</div>
        <div style={styles.chipRow}>
          <div style={styles.chip(!filters.hideInactive)} onClick={toggleActive}>
            active only
          </div>
        </div>
      </div>
    </>
  )
}