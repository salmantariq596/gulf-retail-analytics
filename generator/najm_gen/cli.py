"""Command line entry point.

    najm-gen backfill --profile dev        # reset everything, then simulate the whole window
    najm-gen init --profile full --end 2026-11-21
    najm-gen run --days 1                  # daily incremental mode: simulate the next day
    najm-gen run --until 2026-11-21
    najm-gen status
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from datetime import date, timedelta

from . import config as C
from .sim import State, initial_load, init_state, simulate_day
from .sinks import OnlineSink, PostgresSink


def _reset_outputs() -> None:
    landing = C.LANDING_DIR.resolve()
    if C.DATA_DIR.resolve() not in landing.parents:
        sys.exit(f"Refusing to delete {landing}: not under {C.DATA_DIR}")
    if landing.exists():
        for child in landing.iterdir():
            if child.is_dir() and child == C.ONLINE_DB_PATH.parent.resolve():
                # bind-mounted into the mock-api container: empty it, keep the folder
                for f in child.iterdir():
                    f.unlink()
            elif child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    for checkpoint in (C.STATE_PATH, C.STATE_PATH.with_suffix(".prev")):
        if checkpoint.exists():
            checkpoint.unlink()


def cmd_init(args) -> State:
    profile = C.PROFILES[args.profile]
    end = date.fromisoformat(args.end) if args.end else C.default_end_date()
    start = date.fromisoformat(args.start) if args.start else end - timedelta(days=profile.history_days - 1)
    print(f"Initialising profile={profile.name} window={start}..{end} seed={args.seed}")
    _reset_outputs()
    st = init_state(profile, start, end, args.seed)
    pg, online = PostgresSink(), OnlineSink()
    try:
        initial_load(st, pg, online)
        pg.set_progress(st.current)
        st.save()
        pg.commit()
    finally:
        pg.close()
        online.close()
    print(f"  stores={len(st.stores)} products={len(st.products)} customers={len(st.customers)} "
          f"promotions={len(st.promotions)} campaigns={len(st.campaigns)}")
    return st


def cmd_run(args, st: State | None = None) -> None:
    pg, online = PostgresSink(), OnlineSink()
    t0 = time.time()
    try:
        # the checkpoint must match the day the database has reached (see simulate_day)
        st = st or State.load(expect_next_day=pg.get_progress())
        if args.until:
            until = date.fromisoformat(args.until)
        elif args.days:
            until = st.current + timedelta(days=args.days - 1)
        else:
            until = st.end
        if until < st.current:
            print(f"Nothing to do: next day is {st.current}, until={until}")
            return
        d = st.current
        every = getattr(args, "checkpoint_every", 1) or 1
        while d <= until:
            # with checkpoint_every > 1, a crash between checkpoints means starting again
            checkpoint = d == until or (d - st.start).days % every == 0
            s = simulate_day(st, d, pg, online, checkpoint=checkpoint)
            print(f"  {s['date']}  pos_sales={s.get('pos_sales', 0):>6} lines={s.get('pos_lines', 0):>6} "
                  f"dups={s.get('pos_duplicates', 0):>3} returns={s.get('returns', 0):>4} "
                  f"online={s.get('online_orders', 0):>5} events={s.get('online_events', 0):>5} "
                  f"new_cust={s.get('new_customers', 0):>4} stock={s.get('stock_rows', s.get('stock_file', '-'))}",
                  flush=True)
            d += timedelta(days=1)
    finally:
        pg.close()
        online.close()
    print(f"Done in {time.time() - t0:,.0f}s. Next day to simulate: {st.current}")


def cmd_status(_args) -> None:
    if not C.STATE_PATH.exists():
        print("No generator state. Run `najm-gen init` or `najm-gen backfill` first.")
        return
    st = State.load()
    print(f"profile={st.profile.name} window={st.start}..{st.end} next_day={st.current} "
          f"customers={len(st.customers)} pending_returns={len(st.pending_returns)} "
          f"pending_online_events={len(st.pending_events)}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="najm-gen", description="Najm Retail source data generator")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def window(p):
        p.add_argument("--profile", choices=list(C.PROFILES), default="dev")
        p.add_argument("--start", help="first simulated day (default: end - history_days + 1)")
        p.add_argument("--end", help="last simulated day (default: yesterday)")
        p.add_argument("--seed", type=int, default=int(C.os.getenv("GEN_SEED", "42")))

    window(sub.add_parser("init", help="reset sources and load reference data"))
    backfill = sub.add_parser("backfill", help="init + simulate every day in the window")
    window(backfill)
    backfill.add_argument("--checkpoint-every", type=int, default=1,
                          help="save generator state every N days (use ~30 for the full profile)")
    run = sub.add_parser("run", help="simulate days after the last simulated day (daily mode)")
    run.add_argument("--days", type=int, help="number of days to simulate")
    run.add_argument("--until", help="simulate up to and including this date")
    run.add_argument("--checkpoint-every", type=int, default=1)
    sub.add_parser("status", help="show generator state")

    args = ap.parse_args(argv)
    if args.cmd == "init":
        cmd_init(args)
    elif args.cmd == "backfill":
        st = cmd_init(args)
        args.until, args.days = None, None
        cmd_run(args, st)
    elif args.cmd == "run":
        cmd_run(args)
    elif args.cmd == "status":
        cmd_status(args)


if __name__ == "__main__":
    main()
