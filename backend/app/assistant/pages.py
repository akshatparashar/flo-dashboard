"""What the assistant knows about the dashboard itself: its pages, their filters, and how the screen works.

Everything here describes the dashboard's own features (taken from the frontend and the API); no company facts.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Page:
    key: str                     # API name, e.g. "fabric-po" -> GET /api/fabric-po
    label: str                   # sidebar label
    path: str                    # frontend route
    words: tuple[str, ...]       # how people refer to the page
    about: str                   # one-paragraph description
    filters: dict[str, str] = field(default_factory=dict)   # API filter parameter -> entity type
    order: int = 0               # tie-break: lower wins when two pages show the same figure


PAGES: dict[str, Page] = {p.key: p for p in [
    Page("production", "Production", "/production", ("production", "production page"),
         "Order quantities in production, received and pending pcs, overdue pcs and on-time delivery, by category, "
         "fabricator and month.",
         {"month": "month", "fabricator": "fabricator", "category": "category", "designer": "designer"}, 1),
    Page("fabric-po", "Fabric PO", "/fabric-po", ("fabric po", "po page", "fabric purchase"),
         "Fabric purchase orders: POs raised, fabric ordered, received and pending (mtr), delayed and overdue POs, "
         "vendor scorecard, and the full PO list. A PO counts as delayed when fabric arrives more than 15 days after "
         "the order date.",
         {"month": "month", "vendor": "vendor", "client": "client", "designer": "designer", "item": "category"}, 2),
    Page("fabricator", "Fabricators", "/fabricators", ("fabricators page", "fabricator page", "stock page"),
         "Fabricator stock: fabric issued, pcs under production, received and remaining pcs, and monthly incoming, "
         "per fabricator and month.",
         {"month": "month", "fabricator": "fabricator"}, 3),
    Page("samples", "Samples", "/samples", ("samples page", "sample page", "sample dashboard"),
         "Sample status: approved, rejected, on hold and in process, with approval and rejection rates, by month, "
         "designer and sampling vendor.",
         {"month": "month", "designer": "designer", "vendor": "vendor"}, 4),
    Page("target", "Target & revenue", "/target", ("target page", "revenue page", "target and revenue"),
         "The yearly NEW-order target against what is achieved, plus NEW and REPEAT revenue by month, designer, "
         "item and who ordered.",
         {"month": "month", "designer": "designer", "item": "category", "order_by": "client"}, 5),
    Page("designer", "Designers", "/designers", ("designers page", "designer page", "designer dashboard"),
         "Order volume per designer: new and repeat pcs, share of total, design count, and pcs by category.",
         {"month": "month", "designer": "designer"}, 6),
    Page("client", "Clients", "/clients", ("clients page", "client page", "client dashboard"),
         "Orders per client: order quantity, in production, received and pending pcs by month and category.",
         {"month": "month", "client": "client", "category": "category"}, 7),
    Page("overview", "Overview", "/", ("overview", "home page", "summary page", "main page"),
         "A summary of every sheet: orders, fabricator stock, fabric POs and samples, plus the alerts that need "
         "attention.",
         {"month": "month"}, 8),
]}

# Option lists in the API -> entity type. Other option lists (status, order type, risk...) are not used as names.
OPTION_TYPES = {"designer": "designer", "client": "client", "order_by": "client", "vendor": "vendor",
                "fabricator": "fabricator", "category": "category", "item": "category", "month": "month"}

# First column of a table -> what each row is.
ROW_TYPES = {"designer": "designer", "vendor": "vendor", "fabricator": "fabricator", "month": "month",
             "category": "category", "item name": "category", "item": "category", "order by": "client",
             "client": "client", "po no.": "po", "po no": "po"}

DIMENSION_WORDS = {"designer": "designer", "vendor": "vendor", "client": "client", "fabricator": "fabricator",
                   "month": "month", "category": "category", "po": "po"}

TYPE_NAMES = {"designer": "designer", "vendor": "vendor", "client": "client", "fabricator": "fabricator",
              "category": "category", "month": "month", "po": "PO"}
PLURALS = {"category": "categories", "PO": "POs"}

# The page that "owns" a kind of row, used when a ranking names no measure ("top designer").
HOME_PAGE = {"designer": "designer", "vendor": "fabric-po", "fabricator": "fabricator", "client": "target",
             "category": "production", "month": "production"}

# Questions about how to use the screen. Each entry: trigger words -> answer.
FEATURES = [
    ({"filter", "filters", "filtr"},
     "Every page has filter buttons at the top (month, designer, vendor and so on). Pick one or more values and the "
     "numbers, charts and tables update straight away. Clear a filter to see everything again."),
    ({"download", "csv", "export", "excel"},
     "Tables have a **Download CSV** button under them; it saves exactly the rows you see with the current filters."),
    ({"refresh", "reload", "sync", "update", "updated", "live", "latest"},
     "The dashboard reads the Google Sheets again every minute by itself. The ↻ button in the top bar reads them "
     "right now, and the live light next to it shows when the data was last read."),
    ({"dark", "light", "theme", "mode"},
     "Use the moon / sun button in the top bar to switch between dark and light mode. By default it follows your "
     "device."),
    ({"sidebar", "menu", "collapse", "navigation", "nav"},
     "Pages are in the sidebar on the left. On a PC the sidebar folds into an icon rail with the button in the top "
     "bar (or press **[**). On a phone, open it with the ☰ menu button."),
    ({"login", "passcode", "password", "signin", "sign"},
     "When sign-in is switched on, the dashboard asks for the team passcode once per device."),
    ({"edit", "change", "add", "delete", "modify", "write"},
     "The dashboard is read-only. To change a number, edit the Google Sheet; the dashboard shows the change within "
     "a minute. I can only read the dashboard too."),
]

HELP = ("I answer questions about the numbers and pages of this dashboard, in English or Hinglish. Ask about POs, "
        "pending or received pcs, revenue and target, samples, a designer, client, vendor, fabricator or month. "
        "Add “in one word” for just the number, or “in detail” for a breakdown.")
