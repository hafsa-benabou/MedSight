export default function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect x="3" y="9" width="26" height="14" rx="7" fill="#123B5D" />
      <path d="M16 9h6a7 7 0 0 1 0 14h-6z" fill="#19A78C" />
      <circle cx="16" cy="16" r="4.2" fill="#fff" />
      <circle cx="16" cy="16" r="1.9" fill="#247BA0" />
    </svg>
  );
}
