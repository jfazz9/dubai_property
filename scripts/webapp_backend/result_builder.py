from enquiry_matcher import build_client_response, clean_number

from .owner_lookup import clean_value


def rows_payload(matches_df, price_column):
    columns = [
        "ai_rank",
        "ai_score",
        "ai_fit_summary",
        "ai_opportunity_angle",
        "ai_strengths",
        "ai_concerns",
        "ai_verify",
        "match_score",
        price_column,
        "budget_gap",
        "bedrooms",
        "bathrooms",
        "property_size_sqft",
        "predicted_community",
        "predicted_type",
        "outdoor_matches",
        "match_reasons",
        "title",
        "description",
        "description_json",
        "url",
    ]
    existing_columns = [column for column in columns if column in matches_df.columns]
    rows = []

    for row in matches_df[existing_columns].to_dict("records") if existing_columns else []:
        exclusive_text = " ".join([
            str(row.get("title") or ""),
            str(row.get("description") or ""),
            str(row.get("description_json") or ""),
        ])
        item = {key: clean_value(value) for key, value in row.items()}
        item.pop("description", None)
        item.pop("description_json", None)
        item["has_exclusive_warning"] = has_exclusive_warning(exclusive_text)
        item["price"] = clean_number(item.get(price_column))
        rows.append(item)

    return rows


def has_exclusive_warning(value):
    return "exclusive" in str(value or "").lower()


def duplicate_text_tokens(value):
    text = str(value or "").lower()
    return {
        token
        for token in [
            "single row",
            "vacant soon",
            "vacant",
            "vot",
            "owner occupied",
            "ready to move",
            "large layout",
            "large plot",
            "corner",
            "upgraded",
            "landscaped",
            "type 1",
            "type 2",
            "type 3",
        ]
        if token in text
    }


def likely_duplicate_group_key(item):
    price = clean_number(item.get("price"))
    bedrooms = clean_number(item.get("bedrooms"))
    community = str(item.get("predicted_community") or "").strip().lower()
    property_size = clean_number(item.get("property_size_sqft"))

    if not price or not bedrooms or not community:
        return None

    rounded_price = round(price / 50_000) * 50_000
    rounded_size = round(property_size / 100) * 100 if property_size else ""
    return (community, bedrooms, rounded_price, rounded_size)


def add_similar_listing_warnings(items):
    groups = []

    for item in items:
        key = likely_duplicate_group_key(item)
        tokens = duplicate_text_tokens(" ".join([
            str(item.get("title") or ""),
            str(item.get("predicted_type") or ""),
            str(item.get("outdoor_matches") or ""),
        ]))
        matched_group = None

        for group in groups:
            if key and group["key"] == key:
                matched_group = group
                break

            if key and group["key"] and key[:3] == group["key"][:3] and tokens and len(tokens & group["tokens"]) >= 2:
                matched_group = group
                break

        if matched_group:
            matched_group["items"].append(item)
            matched_group["tokens"].update(tokens)
        else:
            groups.append({
                "key": key,
                "tokens": set(tokens),
                "items": [item],
            })

    similar_urls_by_url = {}

    for group in groups:
        urls = [
            item.get("url")
            for item in group["items"]
            if item.get("url")
        ]

        for url in urls:
            similar_urls_by_url[url] = urls

    warned_items = []

    for item in items:
        item = item.copy()
        urls = similar_urls_by_url.get(item.get("url"), [])
        item["similar_count"] = len(urls)
        item["similar_urls"] = urls
        warned_items.append(item)

    return warned_items


def result_payload(
    enquiry,
    matches_df,
    master_df,
    path,
    ai_result=None,
    premium_compromise_df=None,
    over_budget_df=None,
    fallback_df=None,
):
    response_enquiry = dict(enquiry)
    response_enquiry["bedrooms"] = enquiry["bedrooms"]
    client_response = ai_result.get("client_response") if ai_result else build_client_response(matches_df, response_enquiry)
    price_column = "annual_rent" if enquiry["purpose"] == "rent" else "price"

    payload = {
        "master_file": str(path),
        "rows_searched": int(len(master_df)),
        "enquiry": enquiry,
        "client_response": client_response,
        "matches": add_similar_listing_warnings(rows_payload(matches_df, price_column)),
        "premium_compromise_matches": add_similar_listing_warnings(rows_payload(premium_compromise_df, price_column)) if premium_compromise_df is not None else [],
        "over_budget_matches": add_similar_listing_warnings(rows_payload(over_budget_df, price_column)) if over_budget_df is not None else [],
        "fallback_matches": add_similar_listing_warnings(rows_payload(fallback_df, price_column)) if fallback_df is not None else [],
    }

    if ai_result:
        payload["ai"] = ai_result

    return payload
