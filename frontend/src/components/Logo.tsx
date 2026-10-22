import { useId } from "react";

/** Finzoria leaf mark (Design B): a coral flame-tipped leaf over a lavender leaf, split by a
 * curved gap. Decorative; the wordmark or an accessible name always accompanies it. */
export function LogoMark({ size = 40 }: { size?: number }) {
  const id = useId();
  return (
    <svg className="logo-mark" width={size} height={size} viewBox="0 0 48 48" aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id={`${id}-top`} x1="0" y1="1" x2="1" y2="0">
          <stop offset="0" stopColor="#f2868c" />
          <stop offset="1" stopColor="#fb9c9c" />
        </linearGradient>
        <linearGradient id={`${id}-bottom`} x1="0" y1="1" x2="1" y2="0">
          <stop offset="0" stopColor="#b79cf0" />
          <stop offset="1" stopColor="#d3c3fa" />
        </linearGradient>
      </defs>
      <path
        fill={`url(#${id}-top)`}
        d="M7.2 31.5C6.2 22.6 11.4 13.6 21.2 11.2c3.3-.8 5.4.3 6.9-1.6 1.1-1.4 1.3-3.4 1.1-5.2 2.6 1.8 2.9 5.2 1.3 7.5 3.4-.4 6.6-3 8.8-7.6 2.6 6.3 1.7 12.6-2.4 16.2-4.3 3.7-10.5 3.2-16.8 5.1-5.2 1.6-9.2 3.9-12.9 5.9Z"
      />
      <path
        fill={`url(#${id}-bottom)`}
        d="M6.4 44.6c1.2-5.1 3.6-8.8 7.7-11.2 4.6-2.7 10.5-3 16.3-4.5 6.1-1.6 9.6-4.6 11.6-9.4 1.4 8.3-1.6 15.9-8.9 19.6-5.4 2.8-11.2 1.7-16.6 3.4-3.6 1.1-6.6 2.5-10.1 2.1Z"
      />
    </svg>
  );
}

export function Logo({ name, tagline }: { name: string; tagline?: string }) {
  return (
    <span className="logo">
      <span className="logo-row">
        <LogoMark size={44} />
        <span className="logo-word">{name}</span>
      </span>
      {tagline && <span className="logo-tagline">{tagline}</span>}
    </span>
  );
}
