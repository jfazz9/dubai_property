import argparse
import json
from pathlib import Path

import pandas as pd

from ai_enquiry_ranker import merge_ai_rankings, rank_matches_with_ai
from enquiry_matcher import build_client_response, match_enquiry, parse_bedrooms, parse_budget
from workflow_paths import master_file, normalize_purpose, purpose_dir


def prompt_text(label, default=None):
    suffix = f" [{default}]" if default else ""
    answer = input(f"{label}{suffix}: ").strip()
    return answer or default


def parse_must_haves(value):
    if not value:
        return []

    return [item.strip().lower() for item in value.split(",") if item.strip()]


def safe_filename_part(value, fallback):
    text = str(value or fallback).strip().lower()
    text = "".join(character if character.isalnum() else "_" for character in text)
    text = "_".join(part for part in text.split("_") if part)
    return text or fallback


def default_output_file(purpose, enquiry):
    output_dir = purpose_dir(purpose) / "enquiries"
    output_dir.mkdir(parents=True, exist_ok=True)
    community = safe_filename_part(enquiry.get("community"), "anywhere")
    bedrooms = enquiry.get("bedrooms") or "any"
    budget = enquiry.get("budget") or "any"
    timestamp = pd.Timestamp.now().strftime("%Y-%m-%d_%H-%M")

    return output_dir / f"enquiry_{purpose}_{community}_{bedrooms}bed_{budget}_{timestamp}.csv"


def companion_file(output_file, suffix, extension):
    return output_file.with_name(f"{output_file.stem}_{suffix}{extension}")


def main():
    parser = argparse.ArgumentParser(description="Match a buyer/tenant enquiry against the listing master database.")
    parser.add_argument("--purpose", choices=["sale", "rent"], default="rent")
    parser.add_argument("--master", help="Master CSV to search. Defaults to output/<purpose>/listing_details_master.csv.")
    parser.add_argument("--budget", help="Budget, e.g. 200k or 200000.")
    parser.add_argument("--stretch-budget", help="Stretch budget, e.g. 230k. Defaults to budget.")
    parser.add_argument("--bedrooms", help="Requested bedrooms, e.g. 3 or '3 beds'.")
    parser.add_argument("--community", help="Preferred community, e.g. Casa.")
    parser.add_argument("--must-have", action="append", default=[], help="Must-have keyword. Can be supplied multiple times.")
    parser.add_argument("--must-haves", help="Comma-separated must-haves, e.g. dog,garden.")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--candidate-limit", type=int, default=15, help="Number of rule-ranked candidates to consider before AI ranking.")
    parser.add_argument("--ai", action="store_true", help="Use OpenAI to rank shortlisted rows using full descriptions.")
    parser.add_argument("--ai-model", default="gpt-5-mini", help="OpenAI model for --ai ranking.")
    parser.add_argument("--ai-description-chars", type=int, default=12000, help="Max description characters sent per listing row.")
    parser.add_argument("--output", help="Optional CSV output path for matched listings.")
    args = parser.parse_args()

    purpose = normalize_purpose(args.purpose)
    input_file = Path(args.master) if args.master else master_file(purpose)

    if not input_file.exists():
        raise FileNotFoundError(f"Missing master file: {input_file}")

    budget_text = args.budget or prompt_text("Budget", "200k")
    stretch_budget_text = args.stretch_budget or budget_text
    bedrooms_text = args.bedrooms or prompt_text("Bedrooms", "3")
    community = args.community or prompt_text("Preferred community", "")
    if args.must_haves is not None:
        must_haves_text = args.must_haves
    elif args.must_have:
        must_haves_text = ""
    else:
        must_haves_text = prompt_text("Must-haves, comma separated", "")
    must_haves = args.must_have + parse_must_haves(must_haves_text)

    enquiry = {
        "purpose": purpose,
        "budget": parse_budget(budget_text),
        "stretch_budget": parse_budget(stretch_budget_text),
        "bedrooms": parse_bedrooms(bedrooms_text),
        "community": community,
        "must_haves": must_haves,
    }

    master_df = pd.read_csv(input_file)
    candidate_limit = max(args.limit, args.candidate_limit if args.ai else args.limit)
    matches_df = match_enquiry(master_df, enquiry, limit=candidate_limit)

    output_file = Path(args.output) if args.output else default_output_file(purpose, enquiry)

    ai_result = None

    if args.ai:
        print(f"AI ranking enabled. Sending {len(matches_df)} shortlisted rows to {args.ai_model}.")
        ai_result = rank_matches_with_ai(
            matches_df,
            enquiry,
            model=args.ai_model,
            description_chars=args.ai_description_chars,
        )
        matches_df = merge_ai_rankings(matches_df, ai_result)

    matches_df = matches_df.head(args.limit)
    matches_df.to_csv(output_file, index=False)

    ai_json_file = None
    ai_response_file = None

    if ai_result:
        ai_json_file = companion_file(output_file, "ai", ".json")
        ai_response_file = companion_file(output_file, "ai_response", ".txt")
        ai_json_file.write_text(json.dumps(ai_result, indent=2, ensure_ascii=False), encoding="utf-8")
        ai_response_file.write_text(ai_result.get("client_response", ""), encoding="utf-8")

    print(f"Master file: {input_file}")
    print(f"Rows searched: {len(master_df)}")
    print(f"Matches returned: {len(matches_df)}")
    print(f"Output file: {output_file}")

    if ai_json_file:
        print(f"AI JSON file: {ai_json_file}")
        print(f"AI response file: {ai_response_file}")

    print()

    display_columns = [
        "match_score",
        "annual_rent" if purpose == "rent" else "price",
        "budget_gap",
        "bedrooms",
        "bathrooms",
        "predicted_community",
        "predicted_type",
        "outdoor_matches",
        "agent_name",
        "url",
    ]
    ai_columns = ["ai_rank", "ai_score", "ai_fit_summary", "ai_strengths", "ai_concerns"]
    display_columns = ai_columns + display_columns if args.ai else display_columns
    existing_columns = [column for column in display_columns if column in matches_df.columns]

    if existing_columns:
        print(matches_df[existing_columns].to_string(index=False, max_colwidth=90))
        print()

    print("Suggested response:")

    if ai_result:
        print(ai_result.get("client_response"))
    else:
        print(build_client_response(matches_df, enquiry))


if __name__ == "__main__":
    main()
