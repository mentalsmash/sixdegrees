import os
from enum import Enum
from typing import Generator, Iterable
import datetime
import time

import tmdbsimple as tmdb
from thefuzz import process as fuzzprocess

from .log import Logger as log

tmdb_api_key = os.getenv("TMDB_API_KEY")
if not tmdb_api_key:
  log.warning("No TMDB_API_KEY found")
else:
  tmdb.API_KEY = tmdb_api_key

ApiObject = tmdb.Movies | tmdb.TV | tmdb.People

class ObjectKind(Enum):
  PERSON = 1
  MOVIE = 2
  TV_SERIES = 3

  def __str__(self) -> str:
    return {
      ObjectKind.PERSON: "Person",
      ObjectKind.MOVIE: "Movie",
      ObjectKind.TV_SERIES: "Tv",
    }[self]

  @classmethod
  def parse_media_type(cls, media_type: str):
    return {
      "movie": ObjectKind.MOVIE,
      "tv": ObjectKind.TV_SERIES,
    }[media_type.lower()]

  @property
  def api_cls(self) -> type:
    if self == ObjectKind.PERSON:
      return tmdb.People
    elif self == ObjectKind.MOVIE:
      return tmdb.Movies
    elif self == ObjectKind.TV_SERIES:
      return tmdb.TV

  def load_metadata(self, api: ApiObject) -> dict:
    log.debug("downloading {} metadata: {}", self, api.id)
    if self == ObjectKind.PERSON:
      return {
        "info": api.info(),
        "credits": api.combined_credits(),
      }
    elif self == ObjectKind.MOVIE:
      info = api.info()
      external_ids = api.external_ids()
      info.update(external_ids)
      return {
        "info": info,
        "credits": api.credits(),
      }
    elif self == ObjectKind.TV_SERIES:
      info = api.info()
      external_ids = api.external_ids()
      info.update(external_ids)
      return {
        "info": info,
        "credits": api.credits(),
        "seasons": [],
      }

  @property
  def obj_cls(self) -> "TmdbObject":
    return {
      ObjectKind.PERSON: Person,
      ObjectKind.MOVIE: Movie,
      ObjectKind.TV_SERIES: TvSeries,
    }[self]


  @property
  def table(self) -> str:
    return {
      ObjectKind.PERSON: "people",
      ObjectKind.MOVIE: "movies",
      ObjectKind.TV_SERIES: "tv_series",
    }[self]

  @property
  def graph_table(self) -> str:
    return {
      ObjectKind.MOVIE: "graph_movie",
      ObjectKind.TV_SERIES: "graph_tv",
    }[self]

  @property
  def credits_table(self) -> str:
    return {
      ObjectKind.MOVIE: "movie_credits",
      ObjectKind.TV_SERIES: "tv_credits",
    }[self]


class ObjectId(tuple):
  def __new__(cls, kind: ObjectKind, n: int, metadata: dict | None = None) -> "ObjectId":
    return super(ObjectId, cls).__new__(cls, (kind, n))
  
  def __init__(self, kind: ObjectKind, n: int, metadata: dict | None = None) -> None:
    # super().__init__((kind, n))
    self._metadata = metadata

  def __str__(self) -> str:
    return f"{self.kind}({self.n})"

  @property
  def kind(self) -> ObjectKind:
    return self[0]

  @property
  def n(self) -> int:
    return self[1]

  @property
  def api(self) -> ApiObject:
    return self.kind.api_cls(self.n)

  @property
  def metadata(self) -> dict:
    if self._metadata is None:
      self._metadata = self.kind.load_metadata(self.api)
    return self._metadata

  @metadata.setter
  def metadata(self, metadata: dict) -> None:
    self._metadata = metadata

  @property
  def imdb_id(self) -> int:
    return self.metadata["info"]["imdb_id"]

  @property
  def imdb_url(self) -> str:
    if self.imdb_id is None:
      from urllib.parse import quote
      title = self.metadata["info"].get("name", self.metadata["info"].get("title"))
      if not title:
        return ""
      return f"https://www.imdb.com/find/?q={quote(title)}"

    path = "name" if self.kind == ObjectKind.PERSON else "title"
    return f"https://www.imdb.com/{path}/{self.imdb_id}/"


class TmdbObject:
  def __init__(self, cache: "TmdbCache", id: ObjectId) -> None:
    self._cache = cache
    self.id = id

  def __eq__(self, value: object) -> bool:
    if not isinstance(value, TmdbObject):
      return False
    return value.id == self.id

  def __hash__(self) -> int:
    return hash(self.id)


  @property
  def related(self) -> "Generator[ObjectId, None, None]":
    raise NotImplementedError()

class Person(TmdbObject):
  def __init__(self, cache: "TmdbCache", id: ObjectId) -> None:
    assert(id.kind == ObjectKind.PERSON)
    super().__init__(cache, id)

  def __str__(self) -> str:
    return self.name

  @property
  def name(self) -> str:
    return self.id.metadata["info"]["name"]

  @property
  def imdb_id(self) -> str:
    return self.id.metadata["info"]["imdb_id"]

  @property
  def birthday(self) -> str:
    return self.id.metadata["info"]["birthday"]

  @property
  def deathday(self) -> str | None:
    return self.id.metadata["info"]["deathday"]

  @property
  def profile_path(self) -> str | None:
    return self.id.metadata["info"]["profile_path"]

  @property
  def credits(self) -> list[dict]:
    return self.id.metadata["credits"]["cast"]

  @property
  def related(self) -> "Generator[ObjectId, None, None]":
    for credit in self.credits:
      yield ObjectId(
        kind=ObjectKind.parse_media_type(credit["media_type"]),
        n=credit["id"])


class ActingCredit(TmdbObject):
  def search_characters(self,
      query: str | None = None,
      played_by: ObjectId | None = None,
      **extra_params) -> tuple[list[tuple[int, ObjectId, str, str]], list[tuple[str, int, str]]]:
    raise NotImplementedError()


  def _search_character_credits(self,
      credits: set[tuple[str, int, str]],
      query: str | None = None,
      match_treshold: int = 75,
      results_limit: int = 5,
      **extra_params) -> tuple[list[tuple[int, ObjectId, str, str]], list[tuple[str, int, str]]]:
    result = []
    if query is not None:
      characters = {ch for ch, _, _ in credits}
      ch_match = fuzzprocess.extractBests(query.lower(), characters, score_cutoff = match_treshold, limit = results_limit)
      if ch_match:
        result = sorted({
          (ch_score, ObjectId(ObjectKind.PERSON, pid), pname, ch_name)
          for ch_name, ch_score in ch_match
          for ch, pid, pname in credits if ch == ch_name
        }, key=lambda v: (v[0]*-1, v[2], v[3]))
    else:
      result = list({
        (100, ObjectId(ObjectKind.PERSON, pid), pname, ch)
        for ch, pid, pname in credits
      })

    # if not result:
    #   log.warning("query not found: '{}'", query)
    #   log.warning("available credits:")
    #   for ch_name, pid, pname in sorted(credits, key=lambda v: v[2]):
    #     log.warning("- {}: {} ({})", ch_name, pname, pid)
    #   log.error("[{}, {}] no matching characters for '{}'", self.id, self, query)
    #   raise RuntimeError("no matching characters", query)

    return (result, credits)


class Movie(ActingCredit):
  def __init__(self, cache: "TmdbCache", id: ObjectId) -> None:
    assert(id.kind == ObjectKind.MOVIE)
    super().__init__(cache, id)

  def __str__(self) -> str:
    return self.title

  @property
  def imdb_id(self) -> str:
    return self.id.metadata["info"]["imdb_id"]

  @property
  def original_title(self) -> str:
    return self.id.metadata["info"]["original_title"]

  @property
  def title(self) -> str:
    return self.id.metadata["info"]["title"]

  @property
  def release_date(self) -> str:
    return self.id.metadata["info"]["release_date"]

  @property
  def poster_path(self) -> str | None:
    return self.id.metadata["info"]["poster_path"]

  @property
  def backdrop_path(self) -> str | None:
    return self.id.metadata["info"]["backdrop_path"]

  @property
  def cast(self) -> list[dict]:
    return self.id.metadata["credits"]["cast"]

  @property
  def related(self) -> "Generator[ObjectId, None, None]":
    for cast in self.cast:
      yield ObjectId(
        kind=ObjectKind.PERSON,
        n=cast["id"])

  def search_characters(self,
      query: str | None = None,
      played_by: ObjectId | None = None,
      **extra_params) -> tuple[list[tuple[int, ObjectId, str, str]], list[tuple[str, int, str]]]:
    credits = {
      (c["character"] or "<unknown>", c["id"], c["name"])
      for c in self.cast
      if played_by is None or c["id"] == played_by.id.n
    }
    return self._search_character_credits(credits, query=query, **extra_params)


class TvSeries(ActingCredit):
  def __init__(self, cache: "TmdbCache", id: ObjectId) -> None:
    assert(id.kind == ObjectKind.TV_SERIES)
    super().__init__(cache, id)

  def __str__(self) -> str:
    return self.name

  @property
  def name(self) -> str:
    return self.id.metadata["info"]["name"]

  @property
  def first_air_date(self) -> str:
    return self.id.metadata["info"]["first_air_date"]

  @property
  def last_air_date(self) -> str:
    return self.id.metadata["info"]["last_air_date"]

  @property
  def poster_path(self) -> str | None:
    return self.id.metadata["info"]["poster_path"]

  @property
  def backdrop_path(self) -> str | None:
    return self.id.metadata["info"]["backdrop_path"]

  @property
  def cast(self) -> list[dict]:
    return [
      *self.id.metadata["credits"]["cast"],
      *(
        c
        for season in self.id.metadata["seasons"]
        for ep in season["info"]["episodes"]
        for c in ep["guest_stars"]
      )
    ]

  @property
  def related(self) -> "Generator[ObjectId, None, None]":
    for cast in self.cast:
      yield ObjectId(
        kind=ObjectKind.PERSON,
        n=cast["id"])


  @classmethod
  def parse_episode_id(cls, episode: str) -> tuple[int, int]:
    import re
    episode_str: str = episode.lower()
    if episode_str[0] == "s":
      match_re = re.compile(r"s([0-9]+)e([0-9]+)")
    else:
      match_re = re.compile(r"([0-9]+)x([0-9]+)")
    match = match_re.match(episode_str)
    if not match:
      raise RuntimeError("invalid episode expression", episode)
    season = int(match.group(1))
    episode = int(match.group(2))
    return (season, episode)


  def episode(self, episode: tuple[int, int] | str) -> dict:
    if isinstance(episode, str):
      episode = self.parse_episode_id(episode)
    season_i, episode_i = episode

    season = self.season(season_i)

    if len(season["episodes"]) >= episode_i:
      episode = season["episodes"][episode_i - 1]
      if episode is not None:
        return episode

    log.activity("[{} {}] loading s{}e{}", self.id, self, season_i, episode_i)
    e_api = tmdb.TV_Episodes(self.id.n, season_i, episode_i)
    episode = {
      "info": e_api.info(),
      "credits": e_api.credits()["cast"],
    }

    if len(season["episodes"]) >= episode_i:
      season["episodes"][episode_i - 1] = episode
    else:
      for i in range(0, episode_i - len(season["episodes"]) - 1):
        season["episodes"].append(None)
      season["episodes"].append(episode)

    self._cache.save(self)

    return episode


  def season(self, season: int):
    season_i = season
    if len(self.id.metadata["seasons"]) >= season_i:
      season = self.id.metadata["seasons"][season_i - 1]
      if season is not None:
        return season

    s_api = tmdb.TV_Seasons(self.id.n, season_i)
    log.activity("[{} {}] loading season {}", self.id, self, season_i)
    s_info = s_api.info()
    season = {
      "info": s_info,
      "episodes": []
    }

    if len(self.id.metadata["seasons"]) >= season_i:
      self.id.metadata["seasons"][season_i - 1] = season
    else:
      for i in range(0, season_i - len(self.id.metadata["seasons"]) - 1):
        self.id.metadata["seasons"].append(None)
      self.id.metadata["seasons"].append(season)

    self._cache.save(self)

    return season


  def load_seasons(self, load_episodes: bool = False) -> None:
    for s in self.id.metadata["info"]["seasons"]:
      if s["season_number"] == 0:
        continue
      season = self.season(s["season_number"])
      if load_episodes:
        self.load_episodes(season)

  def load_episodes(self, season: dict) -> None:
    for e in season["info"]["episodes"]:
      _ = self.episode((e["season_number"], e["episode_number"]))


  def search_characters(self,
      query: str | None = None,
      played_by: ObjectId | None = None,
      season: int | None = None,
      episode: tuple[int, int] | str | None = None,
      load_seasons: bool = False,
      load_episodes: bool = False,
      **extra_params) -> tuple[list[tuple[int, ObjectId, str, str]], list[tuple[str, int, str]]]:
    def _season_credits(season):
      if load_episodes:
        self.load_episodes(season)
        credits = [
          c
          for ep in season["episodes"]
          for c in (*ep["credits"], *ep["info"]["guest_stars"])
          if played_by is None or c["id"] == played_by.id.n
        ]
      else:
        credits = [
          c
          for ep in season["info"]["episodes"]
          for c in ep["guest_stars"]
          if played_by is None or c["id"] == played_by.id.n
        ]
        credits += self.id.metadata["credits"]["cast"]
      return credits
    
    query_log_str = (
      ("all " if not query else "") +
      "characters" +
      (f" matching '{query}'" if query else "")
    )

    if episode is not None:
      episode = self.episode(episode)
      credits = [
        c
        for c in (*episode["credits"], *episode["info"]["guest_stars"])
        if played_by is None or c["id"] == played_by.id.n
      ]
      log.info("searching for {} in s{} e{} of {}", query_log_str, episode["info"]["season_number"], episode["info"]["episode_number"], self)
    elif season is not None:
      season = self.season(season)
      credits = _season_credits(season)
      log.info("searching for {} in s{} of {}", query_log_str, season["info"]["season_number"], self)
    else:
      if load_seasons:
        self.load_seasons(load_episodes=load_episodes)
        credits = self.cast
      else:
        credits = self.id.metadata["credits"]["cast"]
      log.info("searching for {} in {}", query_log_str, self)

    credits = {(c["character"] or "<unknown>", c["id"], c["name"]) for c in credits}
    return self._search_character_credits(credits, query=query, **extra_params)


class TmdbCacheBackend:
  def load_object(self, obj_id: ObjectId) -> tuple[ObjectId, int]:
    raise NotImplementedError()

  def save_object(self, obj: TmdbObject) -> None:
    raise NotImplementedError()


_ZeroTimedelta = datetime.timedelta()

class TmdbCache:
  def __init__(self,
      backend: TmdbCacheBackend,
      request_period: int = 20,
      credits: "Iterable[ObjectKind] | None" = None) -> None:
    self._cache = {}
    self._backend = backend
    self._request_period = datetime.timedelta(microseconds=request_period)
    self._last_request_ts = None

  def __getitem__(self, obj_id: ObjectId) -> TmdbObject:
    return self._cache[obj_id][0]

  def __iter__(self):
    return iter(self._cache.keys())

  def __len__(self) -> int:
    return len(self._cache)


  @property
  def people_count(self) -> int:
    return sum((1 for oid in self if oid.kind == ObjectKind.PERSON))

  def save(self, obj: TmdbObject) -> None:
    self._backend.save_object(obj)


  def load(self,
      obj_id: ObjectId,
      cache: bool = False,
      load_seasons: bool = False,
      load_episodes: bool = False) -> tuple[TmdbObject, int]:
    if cache:
      cached = self._cache.get(obj_id)
      if cached is not None:
        return cached

    if self._last_request_ts is not None:
      ts_now = datetime.datetime.now()
      req_delay = ts_now - self._last_request_ts
      min_delay = self._request_period - req_delay
      if min_delay > _ZeroTimedelta:
        min_delay_secs = min_delay.total_seconds()
        log.trace("throttling TMDB API request: {} ms", min_delay_secs * 10**3)
        time.sleep(min_delay_secs)
        self._last_request_ts = datetime.datetime.now()
      else:
        self._last_request_ts = ts_now
        log.trace("TMDB API request period: {} ms", req_delay.total_seconds() * 10**3)

    obj_id, obj_explored_depth = self._backend.load_object(obj_id)
    obj = obj_id.kind.obj_cls(self, obj_id)
    log.activity("loaded {}: {}", obj.id, obj)

    if isinstance(obj, TvSeries) and load_seasons:
      obj.load_seasons(load_episodes=load_episodes)

    entry = (obj, obj_explored_depth)  
    if cache:
      self._cache[obj_id] = entry
      log.debug("cached [{}] {}: {}", obj_explored_depth, obj.id, obj)

    return entry


  def explored_depth(self, obj_id: ObjectId) -> int:
    return self._cache.get(obj_id, (None, 0))[1]


  def explore(self,
      objects: Iterable[ObjectId],
      related_max_depth: int = 1,
      credits_type: "Iterable[ObjectKind] | None" = None,
      load_seasons: bool = False,
      load_episodes: bool = False) -> Iterable[tuple[TmdbObject, int]]:
    enabled_credits = [ObjectKind.MOVIE, ObjectKind.TV_SERIES] if not credits_type else set(credits_type)

    explored_people = {}
    explored_credits = {}

    explorable = set()

    for obj_id in objects:
      obj, explored_depth = self.load(obj_id, load_seasons=load_seasons, load_episodes=load_episodes)
      explorable.add(((obj, explored_depth), 0))

    while len(explorable) > 0:
      (src_obj, explored_depth), start_depth = explorable.pop()

      if src_obj.id.kind == ObjectKind.PERSON:
        explored = explored_people
      else:
        explored = explored_credits
      
      explored_depth = max(explored.get(src_obj.id, 0), explored_depth)

      explorable_depth = related_max_depth - start_depth
      if explorable_depth <= 0:
        explored[src_obj.id] = explored_depth
        log.debug("[{}/{}] -X {}: {} [{}]", start_depth, related_max_depth, src_obj.id, src_obj, explored_depth)
        continue

      # some depth remaining to explore
      log.activity("[{}/{}] -> {}: {} [{}, +{}]",
        start_depth, related_max_depth, src_obj.id, src_obj, explored_depth, explorable_depth)
      
      related_count = 0
      for related_id in src_obj.related:
        rel_depth = start_depth
        if related_id.kind != ObjectKind.PERSON:
          if related_id.kind not in enabled_credits:
            log.activity("[{}/{}]    ! [{}/{}] {} [kind disabled]",
              start_depth, related_max_depth, rel_depth, related_max_depth, related_id)
            continue
          rel_explored = explored_credits
        else:
          rel_depth += 1
          rel_explored = explored_people

        related, rel_explored_depth = self.load(related_id, load_seasons=load_seasons, load_episodes=load_episodes)
        rel_explored_depth = max(rel_explored.get(related.id, 0), rel_explored_depth)
        if rel_explored_depth >= related_max_depth:
          log.activity("[{}/{}]    ! [{}/{}] {}: {} [{} >= {}]",
            start_depth, related_max_depth, rel_depth, related_max_depth, related.id, related, rel_explored_depth, related_max_depth)
          continue

        rel_entry = ((related, rel_explored_depth), rel_depth)
        explorable.add(rel_entry)
        related_count += 1
        log.activity("[{}/{}]    + [{}/{}] {}: {}",
          start_depth, related_max_depth, rel_entry[1], related_max_depth, related.id, related)
      
      explored[src_obj.id] = max(explored_depth, explorable_depth)

      log.activity("[{}/{}]    = +{} [{}]",
        start_depth, related_max_depth, related_count, len(explorable))

    explored = (*explored_people.items(), *explored_credits.items())
    return explored


  def search_tv_series(self, query: str, results_limit: int = 5, first_air_date_year: int | None = None, **extra_params) -> list[TvSeries]:
    result = tmdb.Search().tv(
      query=query,
      **({"first_air_date_year": first_air_date_year} if first_air_date_year is not None else {}))
    matches = {
      r["id"]
      for r in result["results"][:results_limit]
    }
    return [
      self.load(ObjectId(ObjectKind.TV_SERIES, m))[0]
      for m in matches
    ]


  def search_movies(self,
      query: str,
      results_limit: int = 5,
      year: int | None = None,
      primary_release_year: int | None = None,
      **extra_params) -> list[Movie]:
    result = tmdb.Search().movie(
      query=query,
      **({"year": year} if year is not None else {}),
      **({"primary_release_year": primary_release_year} if primary_release_year is not None else {}))
    matches = {
      r["id"]
      for r in result["results"][:results_limit]
    }
    return [
      self.load(ObjectId(ObjectKind.MOVIE, m))[0]
      for m in matches
    ]


  def search_person(self,
      query: str,
      results_limit: int = 5,
      **extra_params) -> list[Person]:
    result = tmdb.Search().person(query=query)
    matches = {
      r["id"]
      for r in result["results"][:results_limit]
    }
    return [
      self.load(ObjectId(ObjectKind.PERSON, m))[0]
      for m in matches
    ]


  def search_characters(self,
      credit: ObjectId | TmdbObject,
      query: str | None = None,
      **extra_params) -> tuple[list[tuple[int, ObjectId, str, str]], list[tuple[str, int, str]]]:
    if isinstance(credit, ObjectId):
      credit = self.load(credit)
    if not isinstance(credit, ActingCredit):
      raise RuntimeError("invalid credit", type(credit))
    return credit.search_characters(query=query, **extra_params)

