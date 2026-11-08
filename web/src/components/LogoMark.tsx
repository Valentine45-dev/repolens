/** The logo mark (public/logo-mark.svg), inline so it takes the text colour: Ink on Paper in light,
 * light on dark in dark. An <img> of the file would stay black on the dark ground. */
export function LogoMark({ size = 20 }: { size?: number }) {
  return (
    <svg
      viewBox="0 0 64 64"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      className="wordmark-mark"
      aria-hidden="true"
    >
      <path d="M19 33 L27 19 L35 33 Z" strokeWidth="2.4" strokeLinejoin="round" />
      <circle cx="27" cy="19" r="3.6" fill="currentColor" stroke="none" />
      <circle cx="19" cy="33" r="3.6" fill="currentColor" stroke="none" />
      <circle cx="35" cy="33" r="3.6" fill="currentColor" stroke="none" />
      <circle cx="27" cy="27" r="19" strokeWidth="5" />
      <path d="M41 41 L56 56" strokeWidth="7" strokeLinecap="round" />
    </svg>
  );
}
