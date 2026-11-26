/* The FLO family of labels, from the LOGOS folder (white-on-navy PDFs, cut to transparent artwork in
   public/brand/world). Each logo is used as a mask and filled with --brand, so it follows the theme. */

export interface Label {
  slug: string;
  name: string; // shown after "FLO"
  ratio: number; // artwork width / height
  live?: boolean;
}

const R = 900 / 490;

export const DASHBOARD: Label = { slug: "dashboard", name: "Dashboard", ratio: R, live: true };

export const LABELS: Label[] = [
  { slug: "community", name: "Community", ratio: R },
  { slug: "basic", name: "Basic", ratio: R },
  { slug: "classic", name: "Classic", ratio: R },
  { slug: "premium", name: "Premium", ratio: R },
  { slug: "exclusive", name: "Exclusive", ratio: R },
  { slug: "vibe", name: "Vibe", ratio: R },
  { slug: "men", name: "Men", ratio: R },
  { slug: "curve", name: "Curve", ratio: R },
  { slug: "uncut", name: "Uncut", ratio: R },
  { slug: "drape", name: "Drape", ratio: R },
  { slug: "roots", name: "Roots", ratio: R },
  { slug: "whats-app", name: "WhatsApp", ratio: R },
  { slug: "deal", name: "Deal", ratio: R },
  { slug: "connect", name: "Connect", ratio: R },
  { slug: "label", name: "Label", ratio: R },
  { slug: "online", name: "Online", ratio: R },
  { slug: "play-learn-grow", name: "Play, Learn & Grow", ratio: R },
  { slug: "people-culture", name: "People & Culture", ratio: R },
  { slug: "care", name: "Care", ratio: R },
  { slug: "outlet", name: "Outlet", ratio: R },
  { slug: "mumbai", name: "Mumbai", ratio: R },
  { slug: "gratitude", name: "Gratitude", ratio: R },
];

export function labelBySlug(slug: string | undefined): Label | undefined {
  return LABELS.find((l) => l.slug === slug);
}

export const logoUrl = (slug: string) => `/brand/world/${slug}.png`;

/** Session flags: the landing plays once per browser session, then "/" opens the dashboard directly. */
export const ENTERED_KEY = "flo-entered";

export function markEntered() {
  try {
    sessionStorage.setItem(ENTERED_KEY, "1");
    sessionStorage.setItem("flo-intro", "1");
  } catch {
    /* ignore */
  }
}

export function hasEntered(): boolean {
  try {
    return sessionStorage.getItem(ENTERED_KEY) === "1";
  } catch {
    return true;
  }
}
