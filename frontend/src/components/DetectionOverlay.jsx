/**
 * DetectionOverlay
 * Renders detected walls (lines), rooms (polygons), and openings (circles)
 * as an SVG layer using the image's native coordinate space.
 * The SVG viewBox matches image dimensions; preserveAspectRatio handles scaling.
 */
export default function DetectionOverlay({ imageUrl, detection }) {
  if (!detection || !imageUrl) return null

  const { walls = [], rooms = [], openings = [], image_size } = detection

  return (
    <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
      {/* Floor plan background */}
      <img
        src={imageUrl}
        alt="Floor plan"
        style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }}
      />

      {/* SVG overlay — coordinate space = image pixel space */}
      <svg
        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}
        viewBox={`0 0 ${image_size.width} ${image_size.height}`}
        preserveAspectRatio="xMidYMid meet"
      >
        <defs>
          <filter id="wall-glow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter>
          <filter id="opening-glow" x="-30%" y="-30%" width="160%" height="160%">
            <feGaussianBlur stdDeviation="4" result="blur" />
            <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter>
        </defs>

        {/* Rooms — subtle translucent fill */}
        {rooms.map((room, i) => {
          const pts = room.polygon.map(([px, py]) => `${px},${py}`).join(' ')
          return (
            <polygon
              key={room.id}
              points={pts}
              fill={`hsla(${(i * 47 + 200) % 360},70%,60%,0.06)`}
              stroke={`hsla(${(i * 47 + 200) % 360},70%,70%,0.35)`}
              strokeWidth="1.5"
              strokeDasharray="6 4"
            />
          )
        })}

        {/* Walls — glowing accent lines */}
        {walls.map(wall => (
          <line
            key={wall.id}
            x1={wall.x1} y1={wall.y1}
            x2={wall.x2} y2={wall.y2}
            stroke="#6378ff"
            strokeWidth="3"
            strokeLinecap="round"
            filter="url(#wall-glow)"
            opacity="0.9"
          />
        ))}

        {/* Wall endpoint dots */}
        {walls.map(wall => (
          <g key={`ep-${wall.id}`}>
            <circle cx={wall.x1} cy={wall.y1} r="4" fill="#6378ff" opacity="0.8" />
            <circle cx={wall.x2} cy={wall.y2} r="4" fill="#6378ff" opacity="0.8" />
          </g>
        ))}

        {/* Openings — door (teal) / window (amber) */}
        {openings.map(op => {
          const wPx = op.width_px || 90
          return (
            <g key={op.id} filter="url(#opening-glow)">
              <circle
                cx={op.x} cy={op.y}
                r={Math.max(8, wPx / 2)}
                fill={op.type === 'door' ? 'rgba(61,217,198,0.18)' : 'rgba(255,193,107,0.18)'}
                stroke={op.type === 'door' ? '#3dd9c6' : '#ffc16b'}
                strokeWidth="2"
              />
              <text
                x={op.x}
                y={op.y - Math.max(12, wPx / 2) - 4}
                textAnchor="middle"
                fontSize="14"
                fill={op.type === 'door' ? '#3dd9c6' : '#ffc16b'}
                fontFamily="Inter, sans-serif"
              >
                {op.type === 'door' ? 'D' : 'W'}
              </text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}
