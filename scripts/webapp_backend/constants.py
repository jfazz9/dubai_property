OWNER_LEADS_FILE = "data/owner_property_leads.csv"
MARKET_SALES_FILE = "data/dxb_market_sales.csv"
MARKET_SALES_PREDICTED_FILE = "data/dxb_market_sales_predicted.csv"
MARKET_RENTALS_FILE = "data/dxb_market_rentals.csv"
MARKET_RENTALS_PREDICTED_FILE = "data/dxb_market_rentals_predicted.csv"
VILLA_TYPE_REFERENCE_FILE = "data/ar2_villa_type_reference.csv"
DEFAULT_RESULT_LIMIT = 20
DEFAULT_AI_RESULT_LIMIT = 10
DEFAULT_AI_SHORTLIST_LIMIT = 12
DEFAULT_AI_BATCH_SIZE = 4
DEFAULT_AI_FINAL_CANDIDATE_LIMIT = 6
AI_DESCRIPTION_CHARS = 700
MARKET_CONTEXT_TRANSACTION_LIMIT = 5
OVER_BUDGET_LIMIT = 5
SALE_OVER_BUDGET_RATIO = 1.40
RENT_OVER_BUDGET_RATIO = 1.25
DEFAULT_SALE_STRETCH_RATIO = 1.08
DEFAULT_RENT_STRETCH_RATIO = 1.15
SALE_BUDGET_FLOOR_RATIO = 0.82
RENT_BUDGET_FLOOR_RATIO = 0.80
COMMUNITY_ALIASES = {
    "arabian ranches 2": "Arabian Ranches 2",
    "arabian ranches ii": "Arabian Ranches 2",
    "ar2": "Arabian Ranches 2",
    "azalea": "Azalea",
    "camelia": "Camelia",
    "casa": "Casa",
    "lila": "Lila",
    "palma": "Palma",
    "rasha": "Rasha",
    "reem": "Reem",
    "rosa": "Rosa",
    "samara": "Samara",
    "yasmin": "Yasmin",
}
MUST_HAVE_TERMS = [
    "bbq",
    "barbecue",
    "dog",
    "pet",
    "garden",
    "pool",
    "single row",
    "corner",
    "vacant",
    "upgraded",
    "furnished",
    "landscaped",
    "large plot",
    "huge plot",
]
VILLA_COMMUNITIES = {"Casa", "Palma", "Samara", "Azalea", "Lila", "Rosa", "Yasmin", "Rasha"}
TOWNHOUSE_COMMUNITIES = {"Camelia", "Reem"}
MARKET_COMMUNITIES = ["Azalea", "Camelia", "Casa", "Lila", "Palma", "Rasha", "Reem", "Rosa", "Samara", "Yasmin"]
SIMILAR_MARKET_GROUPS = [
    {"Azalea", "Samara"},
    {"Casa", "Lila", "Palma"},
    {"Rosa", "Rasha", "Yasmin"},
    {"Camelia", "Reem"},
]
MONTH_ALIASES = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

SCENARIOS = {
    "best_value": {
        "label": "Best Value",
        "report_title": "Best Value Report",
        "focus": (
            "Rank the best value options for the client brief. Compare asking price, price per sqft, "
            "plot/BUA, vacancy, community, predicted type, recent transactions, and active shortlist pricing. "
            "Separate genuine value from listings that are cheap only because they are the wrong product or location."
        ),
    },
    "budget_reality": {
        "label": "Budget Reality",
        "report_title": "Budget Reality Report",
        "focus": (
            "Build a budget reality case. Show whether the client budget is realistic using active listings and recent transactions. "
            "If the requested product is above budget, show realistic options first and explain the market gap clearly."
        ),
    },
    "fallback": {
        "label": "Analyse Fallback",
        "report_title": "Analysed Fallback Options",
        "focus": (
            "Analyse only the fallback townhouse options. Rank the strongest premium compromise first, "
            "then separate stronger premium choices from cheaper budget-saving alternatives. Compare upgrade clues, "
            "single-row/corner/end-unit position, large plot/garden, vacancy, family usability, and value against recent rental transactions. "
            "Explain whether each fallback is a real compromise for a villa client or merely a cheaper townhouse."
        ),
    },
    "negotiation": {
        "label": "Negotiation Case",
        "report_title": "Negotiation Case",
        "focus": (
            "Build a negotiation case for the shortlist. Use market comps, active alternatives, listing age, vacancy, "
            "price per sqft, missing/weak features, size mismatches, and over-budget gaps. Suggest practical offer angles and verification questions."
        ),
    },
    "listing_opportunity": {
        "label": "Listing Opportunity",
        "report_title": "Listing Opportunity Report",
        "focus": (
            "Rank the best listing or poach opportunities. Prioritize non-exclusive listings, owner-lead availability, stale or repeated listings, "
            "vacant stock, price reductions, weak presentation, data mismatches, and owners who may benefit from a sharper pricing strategy."
        ),
    },
    "upgrade_potential": {
        "label": "Upgrade Potential",
        "report_title": "Upgrade Potential Report",
        "focus": (
            "Rank properties with extension, renovation, or value-add potential. Use the collected fields such as predicted_community, "
            "detected_type_from_description, predicted_type, property_size_sqft, plot_size_sqft, bua_from_description, plot_from_description, price_per_sqft, and description_json. "
            "Be type-aware: first use detected_type_from_description if it is present, otherwise use predicted_type. Only compare BUA and extension evidence within the same predicted_community plus same type group. "
            "Do not compare a Casa Type 1 directly with a Casa Type 2 and call the bigger one more extendable; bigger may simply be the natural layout. "
            "For example, a Type 1 can have a larger normal BUA than a Type 2, while the Type 2 may still have better extension potential depending on plot/layout. "
            "Compare similar community/type listings in the supplied rows: if the same type/community sometimes has a larger BUA, larger plot, "
            "or description clues such as extended, extension, upgrade potential, renovate, renovation, investor opportunity, original condition, "
            "blank canvas, large plot, corner, end unit, or big garden, flag it as potential only. Penalize fully turnkey listings unless the plot/BUA "
            "still suggests upside. Be careful: do not state extension is guaranteed; recommend verifying title deed, approvals, developer/community rules, and permissions."
        ),
    },
    "move_in_ready": {
        "label": "Move-in Ready",
        "report_title": "Move-in Ready Report",
        "focus": (
            "Rank the cleanest, lowest-hassle properties for an end user or tenant who wants a nice ready property. Use description_json and all row data. "
            "Prioritize upgraded, renovated, well maintained, immaculate, modern, turnkey, ready to move, vacant, vacant on transfer, furnished, appliances included, "
            "landscaped, owner occupied, new kitchen, clean, and strong maintenance clues. Penalize renovation projects, investor-only wording, needs work, tenanted, "
            "unclear availability, stale condition, and vague descriptions. Recommend verifying actual condition, photos, AC/maintenance, garden condition, and handover date."
        ),
    },
}

CONDITION_FEATURES = [
    ("upgraded downstairs", "upgraded downstairs"),
    ("upgraded kitchen", "upgraded kitchen"),
    ("fully upgraded", "fully upgraded"),
    ("upgraded", "upgraded"),
    ("extension", "extension added"),
    ("extended", "extension added"),
    ("private pool", "private pool"),
    ("pool", "pool"),
    ("landscaped garden", "landscaped garden"),
    ("landscaped", "landscaped garden"),
    ("large garden", "large garden"),
    ("big garden", "large garden"),
    ("good size garden", "large garden"),
    ("corner plot", "corner plot"),
    ("corner", "corner plot"),
    ("single row", "single row"),
    ("end unit", "end unit"),
    ("ready to move", "vacant / ready to move"),
    ("move in ready", "vacant / ready to move"),
    ("vacant on transfer", "vacant / ready to move"),
    ("vacant", "vacant / ready to move"),
    ("excellent finishes", "excellent finishes"),
    ("high end finishes", "high-end finishes"),
    ("good finishes", "good finishes"),
    ("furnished", "furnished"),
    ("unfurnished", "unfurnished"),
]
