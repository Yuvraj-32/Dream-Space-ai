/**
 * DreamSpace brand mark: an arched doorway with a four-point spark cut out of it.
 * One flat colour (currentColor), so it works in any colour, reversed, or in black and white.
 */
export function LogoMark({ size = 28, className = '', title = 'DreamSpace AI' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 96 96" role="img" aria-label={title} className={className}>
      <path
        fill="currentColor"
        fillRule="evenodd"
        d="M20 90V34a28 28 0 0 1 56 0v56zM48 29c1.9 13.6 5.2 18.9 17 22.5-11.8 3.6-15.1 8.9-17 22.5-1.9-13.6-5.2-18.9-17-22.5 11.8-3.6 15.1-8.9 17-22.5z"
      />
    </svg>
  )
}

/** Mark + name, as used in the app header. */
export default function Logo({ size = 28 }) {
  return (
    <span className="brand">
      <LogoMark size={size} className="brand-mark" />
      <span className="brand-name">DreamSpace<span className="brand-ai">AI</span></span>
    </span>
  )
}
