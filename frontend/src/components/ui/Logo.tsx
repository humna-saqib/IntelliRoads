/** Two roads crossing: the product mark. Uses currentColor so it follows the theme. */
export default function Logo({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
      <rect x="3" y="3" width="18" height="18" rx="4.5" />
      <path d="M12 3v18M3 12h18" strokeDasharray="2.2 2.6" />
    </svg>
  );
}
