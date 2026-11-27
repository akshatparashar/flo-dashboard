/* The FLO family of labels (same list as frontend/src/world/brands.ts). Each logo is white artwork on transparent,
   drawn with tintColor so it follows the theme. */
import type { ImageSourcePropType } from "react-native";

export interface Label {
  slug: string;
  /** shown after "FLO" */
  name: string;
  logo: ImageSourcePropType;
}

/** artwork width / height */
export const LOGO_RATIO = 1200 / 656;

export const DASHBOARD: Label = { slug: "dashboard", name: "Dashboard", logo: require("../../assets/world/dashboard.png") };

export const LABELS: Label[] = [
  { slug: "community", name: "Community", logo: require("../../assets/world/community.png") },
  { slug: "basic", name: "Basic", logo: require("../../assets/world/basic.png") },
  { slug: "classic", name: "Classic", logo: require("../../assets/world/classic.png") },
  { slug: "premium", name: "Premium", logo: require("../../assets/world/premium.png") },
  { slug: "exclusive", name: "Exclusive", logo: require("../../assets/world/exclusive.png") },
  { slug: "vibe", name: "Vibe", logo: require("../../assets/world/vibe.png") },
  { slug: "men", name: "Men", logo: require("../../assets/world/men.png") },
  { slug: "curve", name: "Curve", logo: require("../../assets/world/curve.png") },
  { slug: "uncut", name: "Uncut", logo: require("../../assets/world/uncut.png") },
  { slug: "drape", name: "Drape", logo: require("../../assets/world/drape.png") },
  { slug: "roots", name: "Roots", logo: require("../../assets/world/roots.png") },
  { slug: "whats-app", name: "WhatsApp", logo: require("../../assets/world/whats-app.png") },
  { slug: "deal", name: "Deal", logo: require("../../assets/world/deal.png") },
  { slug: "connect", name: "Connect", logo: require("../../assets/world/connect.png") },
  { slug: "label", name: "Label", logo: require("../../assets/world/label.png") },
  { slug: "online", name: "Online", logo: require("../../assets/world/online.png") },
  { slug: "play-learn-grow", name: "Play, Learn & Grow", logo: require("../../assets/world/play-learn-grow.png") },
  { slug: "people-culture", name: "People & Culture", logo: require("../../assets/world/people-culture.png") },
  { slug: "care", name: "Care", logo: require("../../assets/world/care.png") },
  { slug: "outlet", name: "Outlet", logo: require("../../assets/world/outlet.png") },
  { slug: "mumbai", name: "Mumbai", logo: require("../../assets/world/mumbai.png") },
  { slug: "gratitude", name: "Gratitude", logo: require("../../assets/world/gratitude.png") },
];

export function labelBySlug(slug: string | undefined): Label | undefined {
  return LABELS.find((l) => l.slug === slug);
}
