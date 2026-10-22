import { useEffect, useState } from "react";

export const SECTIONS = ["dashboard", "workspace", "payments", "currency", "budget", "funding", "trust", "reports"] as const;
export type Section = (typeof SECTIONS)[number];
/** `hash` optionally targets a tab or a card inside the page (used by Learn More links). */
export type Route =
  | { page: "landing" }
  | { page: "section"; section: Section; hash?: string }
  | { page: "settings"; hash?: string }
  | { page: "learn" };

export function parseRoute(pathname: string): Route {
  const parts = pathname.replace(/\/+$/, "").split("/").filter(Boolean);
  if (parts[0] !== "app") return { page: "landing" };
  if (parts[1] === "settings") return { page: "settings" };
  if (parts[1] === "learn") return { page: "learn" };
  const section = SECTIONS.find((s) => s === parts[1]);
  return { page: "section", section: section ?? "dashboard" };
}

export function hrefFor(route: Route): string {
  const hash = "hash" in route && route.hash ? `#${route.hash}` : "";
  if (route.page === "landing") return "/";
  if (route.page === "settings") return `/app/settings${hash}`;
  if (route.page === "learn") return "/app/learn";
  return `/app/${route.section}${hash}`;
}

export function navigate(route: Route): void {
  window.history.pushState(null, "", hrefFor(route));
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parseRoute(window.location.pathname));
  useEffect(() => {
    // Only the path selects the page; hash changes are handled by the page itself.
    const onPop = () =>
      setRoute((current) => {
        const next = parseRoute(window.location.pathname);
        return JSON.stringify(next) === JSON.stringify(current) ? current : next;
      });
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  return route;
}
