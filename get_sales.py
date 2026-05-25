import argparse
import subprocess
import sys


DEFAULT_LOCATION = "Arabian Ranches 2"
VALID_PURPOSES = ("sale", "rent")


def command_for_step(step, purpose, args):
    python = sys.executable
    scrape_mode = "new-only" if args.quick_new else args.scrape_mode

    if step == "collect":
        command = [
            python,
            "scripts/collect_property_urls.py",
            "--purpose",
            purpose,
            "--location",
            args.location,
            "--manual-wait",
            str(args.collect_wait),
        ]

        if args.quick_new:
            command.extend(["--sort", "newest", "--max-pages", str(args.quick_new_pages)])

        if args.no_beep:
            command.append("--no-beep")

        return command

    if step == "scrape":
        command = [
            python,
            "scripts/scrape_listing_pages.py",
            "--purpose",
            purpose,
            "--manual-wait",
            str(args.scrape_wait),
            "--delay-min",
            str(args.delay_min),
            "--delay-max",
            str(args.delay_max),
            "--scrape-mode",
            scrape_mode,
        ]

        if args.fresh_output:
            command.append("--fresh-output")

        if args.no_resume:
            command.append("--no-resume")

        if args.no_beep:
            command.append("--no-beep")

        return command

    if step == "process":
        return [
            python,
            "scripts/process_listing_data.py",
            "--purpose",
            purpose,
            "--target-area",
            args.location,
        ]

    if step == "predict":
        return [
            python,
            "scripts/predict_villa_type.py",
            "--purpose",
            purpose,
        ]

    if step == "active":
        command = [
            python,
            "scripts/check_active_listings.py",
            "--purpose",
            purpose,
            "--delay",
            str(args.active_delay),
            "--timeout",
            str(args.active_timeout),
        ]

        if args.active_limit:
            command.extend(["--limit", str(args.active_limit)])

        if args.active_dry_run:
            command.append("--dry-run")

        return command

    raise ValueError(f"Unknown step: {step}")


def selected_steps(args):
    steps = []

    if not args.skip_collect:
        steps.append("collect")

    if not args.skip_scrape:
        steps.append("scrape")

    if not args.skip_process:
        steps.append("process")

    if not args.skip_predict:
        steps.append("predict")

    if not args.skip_active_check:
        steps.append("active")

    return steps


def run_command(command, dry_run=False):
    printable = " ".join(f'"{part}"' if " " in part else part for part in command)
    print(f"\n> {printable}", flush=True)

    if dry_run:
        return

    subprocess.run(command, check=True)


def run_purpose(purpose, args):
    print(f"\n=== Refreshing {purpose} listings ===", flush=True)

    for step in selected_steps(args):
        run_command(command_for_step(step, purpose, args), dry_run=args.dry_run)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run the Property Finder collection, scrape, processing, prediction, and active-check workflow."
    )
    parser.add_argument(
        "--purpose",
        choices=["sale", "rent", "both"],
        default="sale",
        help="Which listing workflow to run. Use 'both' to refresh sales and rentals.",
    )
    parser.add_argument("--location", default=DEFAULT_LOCATION, help="Search/target location.")
    parser.add_argument("--collect-wait", type=int, default=60, help="Seconds to wait after manual Find in URL collection.")
    parser.add_argument("--scrape-wait", type=int, default=20, help="Seconds to wait after opening Chrome for scraping.")
    parser.add_argument("--delay-min", type=float, default=5, help="Minimum delay between scraped listing pages.")
    parser.add_argument("--delay-max", type=float, default=10, help="Maximum delay between scraped listing pages.")
    parser.add_argument("--scrape-mode", choices=["new-only", "all"], default="new-only", help="Scrape only new URLs or all URLs.")
    parser.add_argument("--quick-new", action="store_true", help="Collect only newest result pages before running the normal new-only refresh pipeline.")
    parser.add_argument("--quick-new-pages", type=int, default=3, help="Number of newest result pages to collect when --quick-new is used.")
    parser.add_argument("--fresh-output", action="store_true", help="Create a fresh raw scrape output file.")
    parser.add_argument("--no-resume", action="store_true", help="Ignore scraper resume files.")
    parser.add_argument("--active-limit", type=int, help="Only active-check the first N rows.")
    parser.add_argument("--active-delay", type=float, default=0.5, help="Delay between active-check requests.")
    parser.add_argument("--active-timeout", type=int, default=15, help="Active-check request timeout.")
    parser.add_argument("--active-dry-run", action="store_true", help="Run active check without writing the master file.")
    parser.add_argument("--skip-collect", action="store_true", help="Skip URL collection.")
    parser.add_argument("--skip-scrape", action="store_true", help="Skip page scraping.")
    parser.add_argument("--skip-process", action="store_true", help="Skip raw page processing.")
    parser.add_argument("--skip-predict", action="store_true", help="Skip villa type prediction/master update.")
    parser.add_argument("--skip-active-check", action="store_true", help="Skip live listing checks.")
    parser.add_argument("--no-beep", action="store_true", help="Disable audible prompts.")
    parser.add_argument("--dry-run", action="store_true", help="Print the commands without running them.")
    return parser.parse_args()


def main():
    args = parse_args()
    purposes = VALID_PURPOSES if args.purpose == "both" else (args.purpose,)

    for purpose in purposes:
        run_purpose(purpose, args)

    print("\nWorkflow complete.", flush=True)


if __name__ == "__main__":
    main()
