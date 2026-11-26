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
    Page("target", "Designer Order Target", "/target", ("target page", "revenue page", "target and revenue", "target & revenue", "designer order target",
                                                        "order target page"),
         "The yearly NEW-order target against what is achieved, plus NEW and REPEAT revenue by month, designer, "
         "item and who ordered. (Page name before the rename: Target & revenue.)",
         {"month": "month", "designer": "designer", "item": "category", "order_by": "client"}, 5),
    Page("designer", "Designers", "/designers", ("designers page", "designer page", "designer dashboard"),
         "Order volume per designer: new and repeat pcs, share of total, design count, and pcs by category.",
         {"month": "month", "designer": "designer"}, 6),
    Page("client", "Clients Order Status", "/clients", ("clients page", "client page", "client dashboard", "clients order status", "client order status",
                                                  "fw orders", "fw order", "fw order's", "expected deliveries",
                                                  "expected delivery", "delivery by month"),
         "Orders per client: order quantity, in production, received and pending pcs by month and category.",
         {"month": "month", "client": "client", "category": "category"}, 7),
    Page("flo-future", "FLO Future", "/flo-future",
         ("flo future", "future page", "promised", "promises", "promise", "commitment", "commitments", "vaada",
          "outsource", "outsourced", "visits", "meetings", "meeting"),
         "This month's promised samples from the FLO Future sheet (target qty, completed, pending, completion %, "
         "overdue and due-in-3-days items, per designer and team), visits & meetings against what is required each "
         "month, and outsource projects. Pending = Qty Promised − Completed; an item is overdue when its due date has "
         "passed and it is not complete.",
         {"team": "team", "designer": "designer"}, 9),
    Page("vendor-rate", "Vendor Rate", "/vendor-rate",
         ("vendor rate", "vendor rates", "rate list", "rate card", "rate sheet", "fabric rate", "fabric rates",
          "price list"),
         "Fabric rates per vendor from the FABRIC PO 11 sheet: 44\", 60\" and 36\" width rates (₹ per mtr) and "
         "per-piece rates, the cheapest vendor for each fabric category, vendor averages (0 and blank rates left "
         "out) and how much dearer each offering is than the cheapest.",
         {"vendor": "vendor", "fabric": "fabric"}, 10),
    Page("in-out-sale", "In/Out Sale", "/in-out-sale",
         ("in out sale", "in/out sale", "in-out-sale", "inout sale", "sale page", "sales page", "net sale",
          "sale pcs", "sale pieces", "incoming pcs", "incoming pieces", "incoming"),
         "Sale and incoming pieces from the IN/OUT/SALE sheet (2026-27 tab): this year against last year (sale pcs, "
         "sale amount, net sale, net sale per pc), the order -> production -> incoming -> sale flow per month, "
         "fabricator-wise incoming pieces (In-house or Outsource) and the pieces promised for a month against what "
         "came in.",
         {"month": "month", "fabricator": "fabricator"}, 11),
    Page("daily-delegation", "Daily Delegation", "/daily-delegation",
         ("daily delegation", "delegation", "delegation tracker", "daily schedule", "daily tasks", "sir daily", "task list"),
         "Sir's day as a task list from the Daily Schedule tab of the Sir_Daily_Delegation_Tracker sheet: one row per task "
         "with date, responsible person, status (Completed, In Progress, Awaiting Approval, Pending, On Hold) and remarks; "
         "counts are tasks, and 'open for' is days since the task's date.",
         {"person": "person", "status": "status"}, 12),
    Page("overview", "Overview", "/", ("overview", "home page", "summary page", "main page"),
         "A summary of every sheet: orders, fabricator stock, fabric POs and samples, plus the alerts that need "
         "attention.",
         {"month": "month"}, 8),
]}

# Pages added after the original dashboard (the chatbot can summarise "the new sections").
NEW_PAGES = ("flo-future", "vendor-rate", "in-out-sale", "daily-delegation")

# Option lists in the API -> entity type. Other option lists (status, order type, risk...) are not used as names.
OPTION_TYPES = {"designer": "designer", "client": "client", "order_by": "client", "vendor": "vendor",
                "fabricator": "fabricator", "category": "category", "item": "category", "month": "month",
                "team": "team", "fabric": "fabric"}

# First column of a table -> what each row is.
ROW_TYPES = {"designer": "designer", "vendor": "vendor", "fabricator": "fabricator", "month": "month",
             "category": "category", "item name": "category", "item": "category", "order by": "client",
             "client": "client", "po no.": "po", "po no": "po", "team": "team", "fabric category": "fabric"}

DIMENSION_WORDS = {"designer": "designer", "vendor": "vendor", "client": "client", "fabricator": "fabricator",
                   "month": "month", "category": "category", "po": "po", "team": "team"}

# Plural words that ask about every row of a kind ("on-time rate of vendors", "har designer ka revenue").
DIMENSION_PLURALS = {"designers": "designer", "vendors": "vendor", "suppliers": "vendor", "mills": "vendor",
                     "clients": "client", "customers": "client", "parties": "client", "buyers": "client",
                     "fabricators": "fabricator", "karigars": "fabricator", "categories": "category",
                     "items": "category", "products": "category", "teams": "team", "employees": "designer", "staff": "designer"}

# "Best" / "worst" with no measure named: what makes a vendor or fabricator good (higher is better).
QUALITY = {"vendor": "on-time rate", "fabricator": "on-time rate"}

TYPE_NAMES = {"designer": "designer", "vendor": "vendor", "client": "client", "fabricator": "fabricator",
              "category": "category", "month": "month", "po": "PO", "team": "team", "fabric": "fabric"}
PLURALS = {"category": "categories", "PO": "POs", "fabric": "fabric categories"}

# The page that "owns" a kind of row, used when a ranking names no measure ("top designer").
HOME_PAGE = {"designer": "designer", "vendor": "fabric-po", "fabricator": "fabricator", "client": "target",
             "category": "production", "month": "production", "team": "flo-future", "fabric": "vendor-rate"}

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
        "pending or received pcs, revenue and target, samples, this month's FLO Future promises (overdue, due "
        "soon, outsource, meetings), fabric rates (cheapest vendor for crepe, a vendor's rate list), a designer, "
        "team, client, vendor, fabricator or month. "
        "Add “in one word” for just the number, or “in detail” for a breakdown.")
