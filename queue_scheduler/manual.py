"""Manual preview and local state operations. No external service calls."""
import argparse
from .planner import load_names, preview
from .state import transition


def main():
    parser = argparse.ArgumentParser(description="Offline YouTube queue preview and local state ledger.")
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("preview"); p.add_argument("--files-list", required=True); p.add_argument("--output", required=True)
    for action in ("reserve", "complete", "fail", "reconcile"):
        p = commands.add_parser(action); p.add_argument("--files-list", required=True); p.add_argument("--state", required=True); p.add_argument("--filename", required=True)
        if action == "complete": p.add_argument("--youtube-video-id", required=True)
    args = parser.parse_args()
    if args.command == "preview":
        preview(args.files_list, args.output); return
    name = args.filename
    eligible = set(load_names(args.files_list))
    if name not in eligible: raise SystemExit("Refusing: filename is not in the current eligible listing.")
    status = transition(args.state, name, args.command, getattr(args, "youtube_video_id", None))
    print(f"Local state updated for {name}: {status}. No upload or schedule was attempted.")


if __name__ == "__main__":
    main()
