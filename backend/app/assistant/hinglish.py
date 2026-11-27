"""Hinglish replies without an AI model.

When a question is asked in Hinglish ("is mahine ki sales kitni hai"), the answer should come back in Hinglish too.
Gemini does that when a key is set (gemini.phrase). This module is the fallback for when it is not there, is slow,
fails, or changes a figure: it rewrites the assistant's most common answer shapes, line by line, with fixed patterns.

Rules of the rewrite:
- Figures, names, units, month labels and **bold** are copied exactly; only the words around them change.
- A line that matches no pattern keeps its English wording (tables, long explanations), apart from a few fixed
  phrases ("all months so far", "still running") that are swapped wherever they appear.
"""
from __future__ import annotations

import re

_V = r"\*\*[^*]+\*\*"                       # one bold value: **₹4.06 Cr**

# Whole-line patterns, tried in order; the first that matches rewrites the line.
_LINES: list[tuple[re.Pattern, str]] = [
    # Stock Ageing / Unsold Inventory
    (re.compile(rf"^No sale for over (?P<d>\d+) days: (?P<n>{_V}), (?P<q>{_V}), (?P<v>{_V}) at cost \((?P<p>[\d.]+%) of stock value\)\.$"),
     r"\g<d> din se nahi bika: \g<n>, \g<q>, cost par \g<v> (stock value ka \g<p>)."),
    (re.compile(rf"^Never sold \(no sale on record since April 2023\): (?P<n>{_V}), (?P<q>{_V}), (?P<v>{_V}) at cost\. Some may simply be new\.$"),
     r"Kabhi nahi bika (April 2023 se koi sale record nahi): \g<n>, \g<q>, cost par \g<v>. Kuch naye bhi ho sakte hain."),
    (re.compile(rf"^Average age of the stock is (?P<d>{_V}) \(weighted by pieces\)\.$"),
     r"Stock ki average umar \g<d> hai (pcs ke hisaab se)."),
    (re.compile(rf"^(?P<who>{_V}) has the most stock with no sale for over (?P<d>\d+) days: (?P<v>{_V}) \((?P<n>[\d,]+) designs\)\.$"),
     r"\g<d> din se na bikne wala sabse zyada stock \g<who> mein hai: \g<v> (\g<n> designs)."),
    # "Total revenue in November-26 is **₹4.06 Cr**."
    (re.compile(rf"^(?P<label>[^*\n]+?) in (?P<month>[A-Z][a-z]+-\d{{2}}) is (?P<v>{_V})\.$"),
     r"\g<month> mein \g<label> \g<v> hai."),
    # "Total Revenue for **REKHA** is **₹3.76 Cr**."
    (re.compile(rf"^(?P<label>[^*\n]+?) for (?P<who>{_V}) is (?P<v>{_V})\.$"),
     r"\g<who> ka \g<label> \g<v> hai."),
    # "Total POs is **170 POs** (all months so far)."  /  "Pending is **184 pcs** (Nov 2026 promises)."
    (re.compile(rf"^(?P<label>[^*\n]+?) is (?P<v>{_V})(?P<rest> \([^)]*\))?\.$"),
     r"\g<label> \g<v> hai\g<rest>."),
    # "**MAHI EXPORTS** is the fabricator with the highest Pending Pcs: **1,758 pcs**."
    (re.compile(rf"^(?P<who>{_V}) is the (?P<dim>[a-z ]+?) with the (?P<hl>highest|lowest) (?P<label>[^:]+): (?P<v>{_V})\.$"),
     lambda m: f"Sabse {'zyada' if m['hl'] == 'highest' else 'kam'} {m['label']} {m['who']} ({m['dim']}) "
               f"{'ke paas' if re.search(r'pending|stock|remaining', m['label'], re.I) else 'ka'} hai: {m['v']}."),
    # "**January-27** has the most pending pcs in expected deliveries: **5,730 pcs** (of 6,840, all clients)."
    (re.compile(rf"^(?P<who>{_V}) has the (?P<ml>most|least|fewest) (?P<what>.+?)(?: in (?P<where>[^:]+))?: (?P<rest>.+)$"),
     lambda m: f"{m['who']} mein sabse {'zyada' if m['ml'] == 'most' else 'kam'} {m['what']} hain"
               f"{' (' + m['where'] + ')' if m['where'] else ''}: {m['rest']}"),
    # "**Total Revenue** for REKHA and ANAMIKA, added together: REKHA ₹3.76 Cr + ANAMIKA ₹3.35 Cr = **₹7.11 Cr**."
    (re.compile(rf"^(?P<label>{_V}) for (?P<a>.+?) and (?P<b>[^,]+), added together: (?P<rest>.+)$"),
     r"\g<a> aur \g<b> ka \g<label>, dono milakar: \g<rest>"),
    # "Closing stock: **2,046 pcs** in 220 designs, worth **₹27.36 L**; average age 130 days."
    (re.compile(rf"^Closing stock: (?P<q>{_V}) in (?P<n>[\d,]+) designs, worth (?P<v>{_V}); average age (?P<a>[\d,]+) days\.$"),
     r"Closing stock: \g<n> designs mein \g<q>, value \g<v>; average umar \g<a> din."),
    # "Stock over 365 days old: **203 pcs**, **₹2.37 L** at cost (9.9% of pieces, 8.7% of value)."
    (re.compile(rf"^Stock over (?P<d>[\d,]+) days old: (?P<q>{_V}), (?P<v>{_V}) at cost \((?P<p1>[\d.]+%) of pieces, "
                rf"(?P<p2>[\d.]+%) of value\)\.$"),
     r"\g<d> din se purana stock: \g<q>, cost par \g<v> (\g<p1> pcs, \g<p2> value)."),
    # "The cheapest Crepe at 60" width is **PRAGATI MILLS**: NATURAL CREPE at **₹205** per mtr."
    (re.compile(rf"^The (?P<w>cheapest|most expensive|dearest) (?P<f>.+?) at (?P<width>\S+) width is (?P<v>{_V}): (?P<rest>.+)$"),
     lambda m: f"{m['width']} width par sabse {'sasta' if m['w'] == 'cheapest' else 'mehenga'} {m['f']} {m['v']} ka hai: "
               f"{m['rest']}"),
    # "FLO has **122 repeat orders**, totalling **27,270 pcs**."
    (re.compile(rf"^FLO has (?P<n>{_V}), totalling (?P<q>{_V})\.$"), r"FLO ke paas \g<n> hain, kul \g<q>."),
    # "That is 28.37% of all 430 orders (122 ÷ 430 × 100)."
    (re.compile(r"^That is (?P<p>[\d.]+%) of all (?P<all>.+?) (?P<f>\(.+\))\.$"), r"Yeh kul \g<all> ka \g<p> hai \g<f>."),
    # "Target achievement is **65.32%**: achieved (new orders) **₹32.79 Cr** of the yearly target **₹50.20 Cr**."
    (re.compile(rf"^Target achievement is (?P<p>{_V}): achieved \(new orders\) (?P<a>{_V}) of the yearly target (?P<t>{_V})\.$"),
     r"Target achievement \g<p> hai: saal ke target \g<t> mein se \g<a> achieve hua (new orders)."),
    # "Expected in December-26: **1,110 pcs** pending."
    (re.compile(rf"^Expected in (?P<m>[A-Z][a-z]+-\d{{2}}): (?P<q>{_V}) pending\.$"), r"\g<m> mein \g<q> aane baaki hain."),
    (re.compile(r"^Headline numbers right now: (?P<rest>.+)$"), r"Abhi ke main numbers: \g<rest>"),
    # "Top 3 designers by Total Revenue:"
    (re.compile(r"^(?P<tb>Top|Bottom) (?P<n>\d+) (?P<dims>[a-z ]+?) by (?P<label>[^:]+):$"),
     lambda m: f"{m['label']} ke hisaab se {'top' if m['tb'] == 'Top' else 'sabse neeche ke'} {m['n']} {m['dims']}:"),
    # "Total Revenue month by month:"
    (re.compile(r"^(?P<label>[^:\n]+?) month by month:$"), r"\g<label> mahine-wise:"),
    # "Highest: **August-26** (₹5.19 Cr)."
    (re.compile(rf"^Highest: (?P<m>{_V}) (?P<v>\([^)]*\))\.$"), r"Sabse zyada: \g<m> \g<v>."),
    (re.compile(rf"^Lowest: (?P<m>{_V}) (?P<v>\([^)]*\))\.$"), r"Sabse kam: \g<m> \g<v>."),
    # "**Delayed POs** is on the **Fabric PO** page."
    (re.compile(rf"^(?P<what>{_V}) is on the (?P<page>{_V}) page\.$"), r"\g<what> \g<page> page par dikhega."),
    # "**Pending** is **8.3%** of **In production**: 6,858 pcs out of 83,060 pcs."
    (re.compile(rf"^(?P<a>{_V}) is (?P<p>{_V}) of (?P<b>{_V}): (?P<x>.+?) out of (?P<y>.+?)\.$"),
     r"\g<a>, \g<b> ka \g<p> hai: \g<y> mein se \g<x>."),
    # "**REKHA** is higher by **₹1.97 L** (0.5% more than CHARU)."
    (re.compile(rf"^(?P<a>{_V}) is higher by (?P<d>{_V}) \((?P<p>[\d.,]+%) more than (?P<b>[^)]+)\)\.$"),
     r"\g<a> \g<d> se aage hai (\g<b> se \g<p> zyada)."),
    # "**Total revenue** is **₹4.06 Cr** in **November-26**, against **₹4.87 Cr** in **October-26**. That is ..."
    (re.compile(rf"^(?P<label>{_V}) (?:for (?P<who>[^*]*?{_V}|[A-Z][A-Z &]+) )?is (?P<a>{_V}) in (?P<m1>{_V}), against "
                rf"(?P<b>{_V}) in (?P<m2>{_V})\. That is (?P<d>\*\*[^*]+ (?:lower|higher)\*\*), an? "
                rf"(?P<p>\*\*[\d.,]+% (?:decline|growth|increase|decrease)\*\*) compared with (?P<m3>[^.]+)\.$"),
     lambda m: (f"{(m['who'] + ' ka ') if m['who'] else ''}{m['label']} {m['m1']} mein {m['a']} hai, jabki {m['m2']} "
                f"mein {m['b']} tha. Yani {_dir(m['d'])}, {m['m3']} ke mukable {_dir(m['p'])}.")),
]

# Phrases swapped anywhere in a line (after the line patterns), longest first.
_PHRASES = [
    ("(all months so far)", "(ab tak ke sabhi mahine)"),
    ("Designs that have waited longest without a sale:", "Sabse zyada din se na bikne wale designs:"),
    ("Oldest stock, by design (age of the oldest piece still in stock):", "Sabse purana stock, design-wise (sabse purane piece ki umar):"),
    ("Longest without a sale first:", "Sabse zyada din wale pehle:"),
    ("Highest value first:", "Sabse zyada value wale pehle:"),
    ("Unsold stock (designs whose stock has waited without any sale):", "Unsold stock (jin designs ka stock bina sale ke pada hai):"),
    ("all months so far", "ab tak ke sabhi mahine"),
    ("is still running", "abhi chal raha hai"),
    ("so this is not a full-month comparison", "isliye yeh poore mahine ki tulna nahi hai"),
    (", added together:", ", dono milakar:"),
    ("These are **made-up demo rows**: the EasyTrade snapshot is not set up on this server.",
     "Yeh **demo rows** hain (asli data nahi): is server par EasyTrade ka data set nahi hai."),
    ("These are the numbers from your message, not the dashboard's.",
     "Yeh numbers aapke message ke hain, dashboard ke nahi."),
]

_DIR = [("lower", "kam"), ("higher", "zyada"), ("decline", "giravat"), ("decrease", "giravat"),
        ("growth", "badhat"), ("increase", "badhat")]


def _dir(bold: str) -> str:
    for en, hi in _DIR:
        bold = re.sub(rf"\b{en}\b", hi, bold)
    return bold


def _line(line: str) -> str:
    core = line.rstrip()
    for pat, rep in _LINES:
        m = pat.match(core)
        if m:
            core = rep(m) if callable(rep) else m.expand(rep)
            break
    for en, hi in _PHRASES:
        core = core.replace(en, hi)
    return core


def to_hinglish(answer: str) -> str:
    """The answer with its common English sentence shapes rewritten in Hinglish; tables and code are left alone."""
    out = []
    for line in (answer or "").split("\n"):
        out.append(line if line.lstrip().startswith("|") else _line(line))
    return "\n".join(out)


# Greetings and thanks in Hinglish (the English ones live in engine.py).
GREETING = ("Namaste! Main FLO Assistant hoon. Dashboard ke numbers aur pages ke baare mein kuch bhi poochiye, "
            "jaise \"is mahine ki sales kitni hai\", \"sabse zyada pending kis fabricator ke paas hai\", "
            "\"kitne POs overdue hai\" ya \"stock kitna purana hai\". Sirf number chahiye to \"in one word\" likhiye, "
            "poori jaankari ke liye \"in detail\".")
THANKS = "Aapka swagat hai! Dashboard ke baare mein aur kuch poochna ho to bataiye."
