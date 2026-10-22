/** Line icons (24 px grid, currentColor). Decorative unless a label is given. Directional icons
 * carry the "flip" class so they mirror in right-to-left layouts. */
const PATHS = {
  home: "M3.5 10.6 12 3.8l8.5 6.8V20a1 1 0 0 1-1 1H15v-6h-6v6H4.5a1 1 0 0 1-1-1Z",
  sparkle: "M12 3.5l1.9 5.1 5.1 1.9-5.1 1.9L12 17.5l-1.9-5.1L5 10.5l5.1-1.9ZM18.5 15.5l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8ZM5.5 2.5l.6 1.4 1.4.6-1.4.6-.6 1.4-.6-1.4-1.4-.6 1.4-.6Z",
  card: "M3 6.5A1.5 1.5 0 0 1 4.5 5h15A1.5 1.5 0 0 1 21 6.5v11a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 17.5ZM3 10h18M6.5 15h4",
  globe: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm-9 9h18M12 3c2.5 2.6 3.6 5.6 3.6 9s-1.1 6.4-3.6 9c-2.5-2.6-3.6-5.6-3.6-9S9.5 5.6 12 3Z",
  chart: "M5 20V12M10 20V8M15 20v-6M20 20V4",
  cap: "M2.5 9 12 4.5 21.5 9 12 13.5ZM6.5 11v4.5c0 1.6 2.5 3 5.5 3s5.5-1.4 5.5-3V11M21.5 9v5",
  shield: "M12 3 19.5 6v5.5c0 4.6-3.1 8.2-7.5 9.5-4.4-1.3-7.5-4.9-7.5-9.5V6Z",
  doc: "M6 3h8l4 4v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Zm8 0v4h4M8.5 12h7M8.5 16h7",
  gear: "M12 8.8a3.2 3.2 0 1 0 0 6.4 3.2 3.2 0 0 0 0-6.4Zm7.4 3.2c0-.5 0-1-.1-1.4l2-1.6-2-3.4-2.4.9a7.6 7.6 0 0 0-2.4-1.4L14 2.5h-4l-.5 2.6c-.9.3-1.7.8-2.4 1.4l-2.4-.9-2 3.4 2 1.6a7.7 7.7 0 0 0 0 2.8l-2 1.6 2 3.4 2.4-.9c.7.6 1.5 1.1 2.4 1.4l.5 2.6h4l.5-2.6c.9-.3 1.7-.8 2.4-1.4l2.4.9 2-3.4-2-1.6c.1-.4.1-.9.1-1.4Z",
  calendar: "M4 6.5A1.5 1.5 0 0 1 5.5 5h13A1.5 1.5 0 0 1 20 6.5v12a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 18.5ZM4 10h16M8 3v4M16 3v4",
  chevronDown: "m6 9 6 6 6-6",
  arrow: "M4.5 12h15M13.5 6l6 6-6 6",
  wallet: "M4 7.5A2.5 2.5 0 0 1 6.5 5H18v3M4 7.5V17a2 2 0 0 0 2 2h14V8H6.5A2.5 2.5 0 0 1 4 7.5Zm12.5 6.2h.01",
  alert: "M12 3.5 21.5 20h-19ZM12 10v4.5M12 17.3v.01",
  alertCircle: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm0 5v5M12 16v.01",
  checkCircle: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm-4 9.2 2.7 2.6L16.2 9",
  bank: "M3 9.5 12 4l9 5.5M5 10v8M9.5 10v8M14.5 10v8M19 10v8M3 20.5h18",
  list: "M9 6h11M9 12h11M9 18h11M4.5 6h.01M4.5 12h.01M4.5 18h.01",
  plusCircle: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm0 5v8M8 12h8",
  target: "M12 3a9 9 0 1 0 9 9M12 7.5a4.5 4.5 0 1 0 4.5 4.5M12 12l7-7M16 4.5V8h3.5",
  info: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm0 8v5M12 7.8v.01",
  language: "M4 5h9M8.5 3v2M6 5c.6 3.5 2.8 6.3 6 8M11 5c-.7 3.6-3.1 6.6-7 8.5M13 21l4-9 4 9M14.4 18h5.2",
  coins: "M9 4c3.3 0 6 1.3 6 3s-2.7 3-6 3-6-1.3-6-3 2.7-3 6-3ZM3 7v4c0 1.7 2.7 3 6 3s6-1.3 6-3M3 11v4c0 1.7 2.7 3 6 3 1 0 1.9-.1 2.7-.3M15 13c3.3 0 6 1.3 6 3s-2.7 3-6 3-6-1.3-6-3",
  menu: "M4 7h16M4 12h16M4 17h16",
  close: "M6 6l12 12M18 6 6 18",
  receipt: "M6 3h12v18l-3-2-3 2-3-2-3 2ZM9 8h6M9 12h6",
  book: "M4 5.5A1.5 1.5 0 0 1 5.5 4H11v16H5.5A1.5 1.5 0 0 1 4 18.5ZM20 5.5A1.5 1.5 0 0 0 18.5 4H13v16h5.5a1.5 1.5 0 0 0 1.5-1.5Z",
  bus: "M6 3.5h12a1.5 1.5 0 0 1 1.5 1.5v12H4.5V5A1.5 1.5 0 0 1 6 3.5ZM4.5 11h15M7 20v-3M17 20v-3M8 14h.01M16 14h.01",
  food: "M7 3v8M5 3v5a2 2 0 0 0 4 0V3M7 11v10M16 21V3c-2 1-3 3.5-3 7h3",
  phone: "M8 2.5h8A1.5 1.5 0 0 1 17.5 4v16a1.5 1.5 0 0 1-1.5 1.5H8A1.5 1.5 0 0 1 6.5 20V4A1.5 1.5 0 0 1 8 2.5ZM11 18.5h2",
  heart: "M12 20s-7.5-4.6-7.5-10A4.2 4.2 0 0 1 12 7.4 4.2 4.2 0 0 1 19.5 10c0 5.4-7.5 10-7.5 10Z",
  bolt: "M13 3 5 13.5h6L10 21l8-10.5h-6Z",
  user: "M12 4a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM4.5 20c.8-3.6 3.8-6 7.5-6s6.7 2.4 7.5 6",
} as const;

export type IconName = keyof typeof PATHS;

const FLIP: ReadonlySet<IconName> = new Set(["arrow"]);

export function Icon({ name, size = 20, label, className }: { name: IconName; size?: number; label?: string; className?: string }) {
  const classes = ["icon", FLIP.has(name) ? "flip" : "", className ?? ""].filter(Boolean).join(" ");
  return (
    <svg
      className={classes}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      focusable="false"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}

/** Icon for a budget or bill category; unknown categories share a neutral icon. */
export function categoryIcon(category: string): IconName {
  switch (category) {
    case "rent":
    case "housing":
      return "home";
    case "food":
      return "food";
    case "transport":
      return "bus";
    case "phone":
    case "utilities":
      return "phone";
    case "books":
      return "book";
    case "health":
      return "heart";
    case "tuition":
    case "campus":
      return "cap";
    case "transfer_fee":
      return "receipt";
    case "income":
    case "family_contribution":
      return "coins";
    default:
      return "doc";
  }
}
