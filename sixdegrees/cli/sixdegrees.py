from pathlib import Path
import argparse
import re

from sixdegrees.core.log import Logger as log
from sixdegrees.core.database import Database
from sixdegrees.core.fzf import fzf_filter, fzf_interactive_supported, fzf_tab_separated_results_parser
from sixdegrees.core.tmdb import ObjectId, ObjectKind, TmdbObject, Person, ActingCredit

def _load_db(args) -> Database:
  # db = Database(db_file=Path.cwd() / Database.DB_NAME)
  db = Database(db_file=args.database)
  return db

def _load_object(db: Database, query: str, kind: ObjectKind) -> TmdbObject | None:
  try:
    oid = int(query)
    return db.cache.load(ObjectId(kind, oid))[0]
  except ValueError:
    search = {
      ObjectKind.MOVIE: db.cache.search_movies,
      ObjectKind.TV_SERIES: db.cache.search_tv_series,
      ObjectKind.PERSON: db.cache.search_person,
    }[kind]
    return next(iter(search(query, results_limit=1)), None)


def sixdegrees_explore(args):
  db = _load_db(args)

  credits_type = (
    [ObjectKind.MOVIE] if args.credits == "movie" else
    [ObjectKind.TV_SERIES] if args.credits == "tv" else
    None
  )
  objects = (
    *(
      # ObjectId(ObjectKind.PERSON, pid)
      _load_object(db, pid, ObjectKind.PERSON).id
      for pid in args.actor
    ),
    *(
      # ObjectId(ObjectKind.MOVIE, mid)
      _load_object(db, mid, ObjectKind.MOVIE).id
      for mid in args.movie
    ),
    *(
      # ObjectId(ObjectKind.TV_SERIES, tid)
      _load_object(db, tid, ObjectKind.TV_SERIES).id
      for tid in args.tv_series
    ),
  )
  db.explore(objects,
    related_max_depth=args.degree,
    credits_type=credits_type,
    **({"load_episodes": args.thorough >= 2, "load_seasons": args.thorough >= 1} if args.thorough > 0 else {}))


def sixdegrees_wp(args):
  db = _load_db(args)

  if args.movie:
    credit_kind = ObjectKind.MOVIE
    credit_query = args.movie
  elif args.tv_series:
    credit_kind = ObjectKind.TV_SERIES
    credit_query = args.tv_series
  else:
    raise RuntimeError("no movie or tv series specified")

  credit: ActingCredit | None = _load_object(db, credit_query, credit_kind)
  if credit is None:
    log.error("{} credit not found: '{}'", credit_kind.name, credit_query)
    raise RuntimeError("credit not found", credit_kind.name, credit_query)

  extra_params = {
    **({"season": args.season} if args.season is not None else {}),
    **({"episode": args.episode} if args.episode is not None else {}),
    **({"load_episodes": args.thorough >= 2, "load_seasons": args.thorough >= 1} if args.thorough > 0 else {}),
  }

  query = args.character

  matched_actors, candidate_credits = db.cache.search_characters(credit, query=query, **extra_params)
  if not matched_actors:
    log.error("no characters found in '{}' ({}){}",
      credit,
      query,
      credit.id.imdb_url,
      f" matching '{query}'" if query else "")
    if candidate_credits:
      log.warning("{} characters found in '{}':", len(candidate_credits), credit)
      for i, (ch_name, pid, pname) in enumerate(sorted(candidate_credits, key=lambda v: v[2])):
        imdb_str = f" ({ObjectId(ObjectKind.PERSON, pid).imdb_url})" if args.detailed else ""
        log.warning("{}. '{}' played '{}'{}", i + 1, pname, ch_name, imdb_str)
    raise RuntimeError("no matches")

  log.info("{} character{} in '{}' ({}){}",
    len(matched_actors),
    "s" if len(matched_actors) != 1 else "",
    credit,
    credit.id.imdb_url,
    f" match '{query}'" if query else "")
  noninteractive = not fzf_interactive_supported()
  if not noninteractive and False:
    tabs_parser = fzf_tab_separated_results_parser(4)
    def _results_parser(line: str | None) -> "tuple[ObjectId, str, str] | None":
      result = tabs_parser(line)
      if result is None:
        return result
      return (
        result[0],
        ObjectId(ObjectKind.PERSON, result[1]),
        *result[2:]
      )

    selected_actors = fzf_filter(
      inputs=[
        f"{score}\t{actor_id.n}\t{actor_name}\t{ch_name}"
        for score, actor_id, actor_name, ch_name in matched_actors
      ],
      result_parser=_results_parser,
      noninteractive=False,
    )
  else:
    selected_actors = matched_actors

  selected_actors = sorted(selected_actors, key=lambda v: (v[0]*-1, v[2], v[3]))

  if args.limit > 0:
    selected_actors = selected_actors[:args.limit]

  log.info("{} character{} selected from '{}'{}", len(selected_actors), "s" if len(selected_actors) != 1 else "", credit, f" with query '{query}'" if query else "")
  for i, (score, actor_id, actor_name, ch_name) in enumerate(selected_actors):
    imdb_str = f" ({actor_id.imdb_url})" if args.detailed else ""
    log.info("{}/{}. '{}' played '{}'{}{}",
      i + 1, len(selected_actors),
      actor_name, ch_name,
      f" ({score}% match)" if query else "",
      imdb_str)
    if args.print_id:
      print(actor_id.n)


def sixdegrees_whit(args):
  db = _load_db(args)

  actor: Person | None = _load_object(db, args.actor, ObjectKind.PERSON)
  if actor is None:
    log.error("actor not found: '{}'", args.actor)
    raise RuntimeError("actor not found", args.actor)

  if args.movie:
    credit_kind = ObjectKind.MOVIE
    credit_query = args.movie
  elif args.tv_series:
    credit_kind = ObjectKind.TV_SERIES
    credit_query = args.tv_series
  else:
    credit_kind = None

  if credit_kind is not None:
    credit: ActingCredit | None = _load_object(db, credit_query, credit_kind)
    if credit is None:
      log.error("{} credit not found: '{}'", credit_kind.name, credit_query)
      raise RuntimeError("credit not found", credit_kind.name, credit_query)
  else:
    credit = None

  matched_credits = [
    c
    for c in sorted(actor.credits, key=lambda c: c.get("first_air_date", c.get("release_date", 0)))
    for ac in [ObjectId(
      kind=ObjectKind.parse_media_type(c["media_type"]),
      n=c["id"])]
    if credit is None or ac == credit.id
  ]

  if credit is not None:
    if len(matched_credits) > 0:
      if len(matched_credits) == 1:
        log.info("'{}' ({}) was in '{}' ({}) as {}", actor, actor.id.imdb_url, credit, credit.id.imdb_url, f"'{matched_credits[0]['character'] or '<unknown>'}'")
      else:
        characters = sorted({
          c["character"] or '<unknown>' for c in matched_credits
        })
        log.info("'{}' ({}) was in '{}' ({}) as {}", actor, actor.id.imdb_url, credit, credit.id.imdb_url, f"{len(characters)} characters:")
        for i, ch in enumerate(characters):
          log.info("{}/{}. '{}'", i+1, len(characters), ch)

    else:
      log.error("it doesn't seem like '{}' ({}) was in '{}' ({})", actor, actor.id.imdb_url, credit, credit.id.imdb_url)
      raise RuntimeError("credit not found")
  elif len(matched_credits) == 0:
    log.error("it doesn't seem like '{}' ({}) has acted in anything", actor, actor.id.imdb_url)
    raise RuntimeError("actor has no credits")
  else:
    log.info("showing {}{} role{} played by '{}' ({}):",
      "all " if len(matched_credits) > 1 else "",
      len(matched_credits),
      "s" if len(matched_credits) > 1 else "",
      actor,
      actor.id.imdb_url)
    for i, actor_credit in enumerate(matched_credits):
      actor_credit_id = ObjectId(ObjectKind.parse_media_type(actor_credit["media_type"]), actor_credit["id"])
      credit_title = actor_credit.get("title", actor_credit.get("name", None))
      if not args.detailed:
        detailed_str = ""
      else:
        detailed_str = f" ({actor_credit_id.imdb_url})"
      log.info("{}/{}. '{}' ({}), as '{}'{}",
        i + 1,
        len(matched_credits),
        credit_title,
        actor_credit.get("first_air_date", actor_credit.get("release_date", 0)),
        actor_credit["character"] or "<unknown>",
        detailed_str)


def _parser_explore(cmd_explore):
  cmd_explore.add_argument("-D", "--degree",
    help="Maximum degree of separation to consider.",
    type=int,
    default=1)

  cmd_explore.add_argument("-t", "--thorough",
    help="Perform a thorough search. Repeat to be more thorough.",
    action="count",
    default=0)

  cmd_explore.add_argument("-c", "--credits",
    help="Type of credits to consider.",
    choices=["all", "movie", "tv"],
    default="all")

  cmd_explore.add_argument("-A", "--actor",
    metavar="TMDB_ID",
    help="Name or TMDB id of an actor.",
    # type=int,
    default=[],
    action="append")

  cmd_explore.add_argument("-M", "--movie",
    metavar="TMDB_ID",
    help="Name or TMDB id of a movie.",
    # type=int,
    default=[],
    action="append")

  cmd_explore.add_argument("-T", "--tv-series",
    metavar="TMDB_ID",
    help="Name or TMDB id of a TV series.",
    # type=int,
    default=[],
    action="append")


def _parser_wp(cmd_wp):

  mut_group = cmd_wp.add_mutually_exclusive_group()
  mut_group.add_argument("-M", "--movie",
    metavar="TITLE",
    help="Movie title or TMDB id.",
    default=None)
  mut_group.add_argument("-T", "--tv-series",
    metavar="TITLE",
    help="TV Series title or TMDB id.",
    default=None)

  mut_group = cmd_wp.add_mutually_exclusive_group()
  mut_group.add_argument("-s", "--season",
    metavar="SEASON_NUMBER",
    help="Season of a TV Series",
    type=int,
    default=None)
  mut_group.add_argument("-e", "--episode",
    metavar="EPISODE_ID",
    help="Episode of a TV Series. Accepted formats: NxM, sNeM",
    default=None)

  cmd_wp.add_argument("-t", "--thorough",
    help="Perform a thorough search. Repeat to be more thorough.",
    action="count",
    default=0)

  cmd_wp.add_argument("-l", "--limit",
    help="Maximum number of results to consider. Default: %(default)s (unlimited).",
    type=int,
    default=0)

  cmd_wp.add_argument("-D", "--detailed",
    help="Download and print more detailed information (e.g. actors IMDB links).",
    action="store_true",
    default=False)

  cmd_wp.add_argument("-i", "--print-id",
    help="Print the TMDB id of matched actors to stdout.",
    action="store_true",
    default=False)

  # cmd_wp.add_argument("-m", "--multi",
  #   help="Return multiple results if available.",
  #   action="store_true",
  #   default=False)

  # cmd_wp.add_argument("-i", "--print-id",
  #   help="Print matching actors TMDB id to stdout.",
  #   action="store_true",
  #   default=False)

  cmd_wp.add_argument("character",
    metavar="CHARACTER_NAME",
    help="Name of the character played by the actor to match.",
    default=None,
    nargs="?")

def _parser_whit(cmd_whit):
  mut_group = cmd_whit.add_mutually_exclusive_group()
  mut_group.add_argument("-M", "--movie",
    metavar="TITLE",
    help="Movie title or TMDB id.",
    default=None)
  mut_group.add_argument("-T", "--tv-series",
    metavar="TITLE",
    help="TV Series title or TMDB id.",
    default=None)

  mut_group = cmd_whit.add_mutually_exclusive_group()
  mut_group.add_argument("-s", "--season",
    metavar="SEASON_NUMBER",
    help="Season of a TV Series",
    type=int,
    default=None)
  mut_group.add_argument("-e", "--episode",
    metavar="EPISODE_ID",
    help="Episode of a TV Series. Accepted formats: NxM, sNeM",
    default=None)

  cmd_whit.add_argument("-D", "--detailed",
    help="Download and print more detailed information (e.g. credit IMDB links).",
    action="store_true",
    default=False)

  cmd_whit.add_argument("actor",
    metavar="ACTOR_NAME",
    help="Name of the actor to match or TMDB ID.",
    default=None,
    nargs="?")


def common_arguments(parser):
  parser.add_argument(
    "-v",
    "--verbose",
    action="count",
    default=0,
    help="Increase output verbosity. Repeat for increased verbosity.",
  )
  parser.add_argument("-d", "--database",
    metavar="DB_FILE",
    help="Path to a permanent database file.",
    default=None,
    type=Path)


def define_parser():
  parser = argparse.ArgumentParser("6d",
    description="Command-line interface to explore work connections between actors.")
  parser.set_defaults(cmd=None)

  subparsers = parser.add_subparsers()

  # cmd_explore = subparsers.add_parser("explore")
  # cmd_explore.set_defaults(cmd=sixdegrees_explore)
  # common_arguments(cmd_explore)
  # _parser_explore(cmd_explore)

  cmd_wp = subparsers.add_parser("cast", aliases=["c",])
  cmd_wp.set_defaults(cmd=sixdegrees_wp)
  common_arguments(cmd_wp)
  _parser_wp(cmd_wp)

  cmd_whit = subparsers.add_parser("credits", aliases=["C"])
  cmd_whit.set_defaults(cmd=sixdegrees_whit)
  common_arguments(cmd_whit)
  _parser_whit(cmd_whit)

  return parser


def main():
  parser = define_parser()
  args = parser.parse_args()

  log.min_level = args.verbose + 1

  if args.cmd is None:
    raise RuntimeError("no command specified")

  args.cmd(args)
