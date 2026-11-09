/**
 * Small inline SVG icon set (stroke icons, 24px grid) so the UI doesn't rely on
 * emoji, which render differently on every OS. Usage: <Icon name="upload" size={16} />
 */
const PATHS = {
  logo: <><path d="M3 10.5 12 4l9 6.5" /><path d="M5 9v10.5h14V9" /><path d="M10 19.5v-5h4v5" /></>,
  upload: <><path d="M12 15V4" /><path d="m7 9 5-5 5 5" /><path d="M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4" /></>,
  file: <><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /></>,
  drawing: <><rect x="3" y="3" width="18" height="18" rx="2" /><path d="M3 10h8v11" /><path d="M11 14h10" /></>,
  scan: <><path d="M4 8V5a1 1 0 0 1 1-1h3" /><path d="M16 4h3a1 1 0 0 1 1 1v3" /><path d="M20 16v3a1 1 0 0 1-1 1h-3" /><path d="M8 20H5a1 1 0 0 1-1-1v-3" /><path d="M4 12h16" /></>,
  edit: <><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" /></>,
  cube: <><path d="m21 16-9 5-9-5V8l9-5 9 5z" /><path d="m3 8 9 5 9-5" /><path d="M12 13v8" /></>,
  walk: <><circle cx="13" cy="4" r="2" /><path d="m9 20 3-6 3 3v4" /><path d="m6 12 3-4 4 1 3 3" /></>,
  play: <path d="M7 4v16l13-8z" />,
  present: <><rect x="3" y="4" width="18" height="12" rx="1.5" /><path d="M12 16v4" /><path d="M8 20h8" /></>,
  orbit: <><circle cx="12" cy="12" r="3" /><ellipse cx="12" cy="12" rx="10" ry="4.5" /></>,
  check: <path d="m5 12 5 5L20 7" />,
  checkCircle: <><circle cx="12" cy="12" r="9" /><path d="m8 12 3 3 5-6" /></>,
  alert: <><path d="M12 9v4" /><path d="M12 17h.01" /><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" /></>,
  x: <><path d="M18 6 6 18" /><path d="m6 6 12 12" /></>,
  arrowRight: <><path d="M5 12h14" /><path d="m13 6 6 6-6 6" /></>,
  cursor: <path d="m4 4 7 17 2.5-7.5L21 11z" />,
  pen: <><path d="M3 21 21 3" /><circle cx="3" cy="21" r="1.5" /><circle cx="21" cy="3" r="1.5" /></>,
  trash: <><path d="M4 7h16" /><path d="M10 11v6M14 11v6" /><path d="M6 7l1 13h10l1-13" /><path d="M9 7V4h6v3" /></>,
  wall: <><rect x="3" y="5" width="18" height="14" rx="1" /><path d="M3 12h18M9 5v7M15 12v7" /></>,
  room: <><rect x="3" y="3" width="18" height="18" rx="2" /><path d="M3 12h9V3" /></>,
  door: <><path d="M5 21V4a1 1 0 0 1 1-1h9v18" /><path d="M3 21h18" /><path d="M12 12h.01" /></>,
  window: <><rect x="4" y="3" width="16" height="18" rx="1" /><path d="M12 3v18M4 12h16" /></>,
  ruler: <><path d="M3 17 17 3l4 4L7 21z" /><path d="m7 13 2 2M10 10l2 2M13 7l2 2" /></>,
  sparkles: <><path d="M12 3v4M12 17v4M3 12h4M17 12h4" /><path d="m6 6 2 2M16 16l2 2M6 18l2-2M16 8l2-2" /></>,
  info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></>,
}

export default function Icon({ name, size = 16, strokeWidth = 1.75, className = '', ...rest }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={`icon ${className}`}
      {...rest}
    >
      {PATHS[name]}
    </svg>
  )
}
