from pathlib import Path
import sqlite3
import json
from importlib.resources import files, as_file
import tempfile
from collections import namedtuple
from enum import Enum
from contextlib import contextmanager
from typing import Generator, Iterable

from ..data import database as db_data
from .log import Logger as log
from .tmdb import (
  ObjectId,
  ObjectKind,
  TmdbCache,
  TmdbCacheBackend,
  TmdbObject,
  Person,
)

def namedtuple_factory(cursor, row):
  fields = [column[0] for column in cursor.description]
  cls = namedtuple("Row", fields)
  return cls._make(row)

def _get_sqlite3_thread_safety():
  # Map value from SQLite's THREADSAFE to Python's DBAPI 2.0
  # threadsafety attribute.
  sqlite_threadsafe2python_dbapi = {0: 0, 2: 1, 1: 3}
  conn = sqlite3.connect(":memory:")
  threadsafety = conn.execute(
    """
select * from pragma_compile_options
where compile_options like 'THREADSAFE=%'
"""
  ).fetchone()[0]
  conn.close()

  threadsafety_value = int(threadsafety.split("=")[1])

  return sqlite_threadsafe2python_dbapi[threadsafety_value]

class DatabaseTable(Enum):
  ACTORS = 1
  OPPORTUNITIES = 2
  JOBS = 3

class Database(TmdbCacheBackend):
  Cursor = sqlite3.Cursor

  DB_NAME = "sixdegrees.db"

  THREAD_SAFE = _get_sqlite3_thread_safety()

  def __init__(self,
      db_file: Path | None = None) -> None:
    assert self.THREAD_SAFE
    if db_file is None:
      self.tmp_root = tempfile.TemporaryDirectory()
      self.db_file = Path(self.tmp_root.name) / self.DB_NAME
    else:
      self.db_file = db_file

    create = False
    if not self.db_file.exists():
      self.db_file.parent.mkdir(parents=True, exist_ok=True)
      self.db_file.touch()
      create = True

    self._transaction_cursor = None
    self._db = sqlite3.connect(
      self.db_file,
      isolation_level="DEFERRED",
      detect_types=sqlite3.PARSE_DECLTYPES,
      check_same_thread=False,
    )

    self._db.row_factory = namedtuple_factory
    def _tracer(query) -> None:
      log.tracedbg("exec SQL:\n{}", query)
    self._db.set_trace_callback(_tracer)

    if create:
      self.initialize()
    else:
      log.activity("loaded DB: {}", self.db_file)

    self.cache = TmdbCache(self)


  @contextmanager
  def transaction(self) -> Generator[sqlite3.Cursor, None, None]:
    if self._transaction_cursor is not None:
      raise RuntimeError("transaction already in progress")
    with self._db:
      self._transaction_cursor = self._db.cursor()
      yield self._transaction_cursor
    self._transaction_cursor = None


  def cursor(self) -> sqlite3.Cursor:
    if self._transaction_cursor is not None:
      return self._transaction_cursor
    else:
      return self._db.cursor()


  def _load_cache(self) -> None:
    log.activity("loading DB cache...")
    with self.transaction() as cursor:
      for obj_kind in ObjectKind:
        for row in cursor.execute(f"SELECT id FROM {obj_kind.table}").fetchall():
          obj_id = ObjectId(obj_kind, row.id)
          self.cache.load(obj_id)
    log.activity("loaded DB cache: {} records", len(self.cache))


  def load_object(self, obj_id: ObjectId) -> tuple[ObjectId, int]:
    if obj_id.kind == ObjectKind.PERSON:
      existing = self.find_person(obj_id.n)
    elif obj_id.kind == ObjectKind.MOVIE:
      existing = self.find_movie(obj_id.n)
    elif obj_id.kind == ObjectKind.TV_SERIES:
      existing = self.find_tv_series(obj_id.n)
    if existing is not None:
      obj_id.metadata = json.loads(existing.metadata)
      explored_depth = existing.explored_depth
      log.debug("already in local DB: id={}, depth={}", obj_id, explored_depth)
    else:
      def _save():
        query = [
          f"INSERT INTO {obj_id.kind.table} (id, metadata, explored_depth) VALUES (?, ?, ?)",
          (obj_id.n, json.dumps(obj_id.metadata), 0)
        ]
        log.debug("add to local DB: id={}", obj_id)
        cursor = self.cursor()
        cursor.execute(*query)
      if self._transaction_cursor is None:
        with self._db:
          _save()
      else:
        _save()
    return [obj_id, 0]


  def save_object(self, obj: TmdbObject) -> None:
    def _save():
      query = [
        f"UPDATE {obj.id.kind.table} SET metadata = ? WHERE id = ?",
        (json.dumps(obj.id.metadata), obj.id.n)
      ]
      cursor = self.cursor()
      cursor.execute(*query)
      log.debug("updated in DB: {}", obj.id, obj)
    if self._transaction_cursor is None:
      with self._db:
        _save()
    else:
      _save()


  def explore(self,
      objects: Iterable[ObjectId],
      related_max_depth: int = 1,
      credits_type: "Iterable[ObjectKind] | None" = None,
      **extra_args) -> set[TmdbObject]:
    objects = set(objects)
    log.activity("load {} into DB @[{}]: {}", len(objects), related_max_depth, objects)
    result = set()
    with self.transaction() as cursor:
      explored_objects = self.cache.explore(objects, related_max_depth=related_max_depth, credits_type=credits_type, **extra_args)
      for explored_id, explored_depth in explored_objects:
        loaded, _ = self.cache.load(explored_id)
        cursor.execute(
          f"UPDATE {loaded.id.kind.table} SET  explored_depth = ? WHERE id = ?",
          (explored_depth, loaded.id.n))
        if explored_id in objects:
          result.add(loaded)
    log.info("loaded {}@[{}]:", len(result), related_max_depth)
    for i, r in enumerate(result):
      log.info("[{}] {}: {}", i+1, r.id, r)
    return result


  def initialize(self) -> None:
    for script in ["database_init.sql"]:
      with as_file(files(db_data).joinpath(script)) as sql:
        self._db.executescript(sql.read_text())
    log.activity("initialized DB: {}", self.db_file)


  def find_person(self, db_id: int) -> tuple | None:
    query = "SELECT * FROM people WHERE id = ?"
    cursor = self.cursor()
    return cursor.execute(query, (db_id,)).fetchone()


  def find_movie(self, db_id: int) -> tuple | None:
    query = "SELECT * FROM movies WHERE id = ?"
    cursor = self.cursor()
    return cursor.execute(query, (db_id,)).fetchone()


  def find_tv_series(self, db_id: int) -> tuple | None:
    query = "SELECT * FROM tv_series WHERE id = ?"
    cursor = self.cursor()
    return cursor.execute(query, (db_id,)).fetchone()


  def update_credits(self) -> None:
    with self.transaction() as cursor:
      obj_i = 0
      for obj_kind in ObjectKind:
        if obj_kind != ObjectKind.PERSON and obj_kind not in self.cache._enabled_credits:
          continue
        for row in cursor.execute(f"SELECT id FROM {obj_kind.table}").fetchall():
          obj_id = ObjectId(obj_kind, row.id)
          obj, _ = self.cache.load(obj_id)

          contained_count = 0
          if obj_kind == ObjectKind.PERSON:
            for credit in obj.credits:
              credit_kind = ObjectKind.parse_media_type(credit["media_type"])
              if credit_kind not in self.cache._enabled_credits:
                continue
              contained_count += 1
              cursor.execute(
                f"INSERT INTO {credit_kind.credits_table} VALUES (?, ?) "
                "ON CONFLICT(actor, job) DO NOTHING",
                (obj.id.n, credit["id"]))
          else:
            for cast in obj.cast:
              contained_count += 1
              cursor.execute(
                f"INSERT INTO {obj_kind.credits_table} VALUES (?, ?) "
                "ON CONFLICT(actor, job) DO NOTHING",
                (cast["id"], obj.id.n))
          log.info("[{}] -> {}: {} [{}]", obj_i + 1, obj.id, obj, contained_count)
          obj_i += 1


  def build_credits_graph(self, actors: "Iterable[int] | None" = None, credits: "Iterable[ObjectKind] | None" = None):
    vertices = set()
    edges = set()

    if credits is None:
      credits = [ObjectKind.MOVIE, ObjectKind.TV_SERIES]

    log.warning("building graph...")

    with self.transaction() as cursor:      
      if actors is None:
        actors = set()
        for credit_kind in credits:
          for row in cursor.execute(f"SELECT DISTINCT actor from {credit_kind.credits_table}").fetchall():
            actors.add(row.actor)
      
      for i, actor in enumerate(actors):
        for credit_kind in credits:
          jobs = cursor.execute(f"SELECT job from {credit_kind.credits_table} WHERE actor = ?", (actor,)).fetchall()
          log.info("[{}/{}] actor {}, jobs: {}", i+1, len(actors), actor, len(jobs))
          for row in jobs:
            for other_actor in cursor.execute(f"SELECT actor from {credit_kind.credits_table} WHERE job = ? AND actor != ?", (row.job, actor,)).fetchall():
              a = min(actor, other_actor.actor)
              b = other_actor.actor if a == actor else actor
              edges.add((a, b, row.job))
              vertices.add(a)
              vertices.add(b)

    log.warning("graph: {} verticies, {} edges", len(vertices), len(edges))


  # def find_actor_opportunities(self, actor: int, load: bool = False) -> Generator[namedtuple, None, None]:
  #   if load:
  #     fields = ["id", "type", "name"]
  #   else:
  #     fields = ["id"]
  #   query = (
  #     f"SELECT {', '.join(fields)} FROM acting_jobs JOIN acting_opportunities "
  #     "WHERE acting_jobs.actor = ? AND acting_jobs.opportunity = acting_opportunities.id"
  #   )
  #   log.tracedbg("find opportunities for actor: {} (load={})", actor, load)
  #   cursor = self._db.cursor()
  #   for row in cursor.execute(query, (actor,)):
  #     yield row

  # def find_opportunity_actors(self, opportunity: int, load: bool = False) -> Generator[namedtuple, None, None]:
  #   if load:
  #     fields = ["id", "name"]
  #   else:
  #     fields = ["id"]
  #   query = (
  #     f"SELECT {', '.join(fields)} FROM acting_jobs JOIN actors "
  #     "WHERE acting_jobs.opportunity = ? AND acting_jobs.actor = actors.id"
  #   )
  #   log.tracedbg("find actors for opportunity: {} (load={})", opportunity, load)
  #   cursor = self._db.cursor()
  #   for row in cursor.execute(query, (opportunity,)):
  #     yield row

  # def insert_actor(self,
  #     actor: "Actor",
  #     opportunities: "list[Opportunity] | None" = None) -> None:
  #   query = "INSERT INTO actors SET (id, name) VALUES (?, ?)"

  #   with self._db:
  #     cursor = self._db.cursor()
  #     cursor.execute(query, (actor.id, actor.name))
  #     if opportunities:
  #       self.insert_actor_opportunities(actor.id, opportunities, cursor=cursor)

  # def insert_actor_opportunities(self,
  #     actor: int,
  #     opportunities: "list[Opportunity]",
  #     cursor = None):
  #   if cursor is None:
  #     cursor = self._db.cursor()
  #   query = "INSERT INTO acting_opportunities SET (actor, opportunity) VALUES (?, ?)"
  #   cursor.executemany(query, [
  #     (actor, opp.id) for opp in opportunities
  #   ])

  # def insert_opportunity(self,
  #     opportunity: "Opportunity",
  #     actors: list[int] | None = None):
  #   query = "INSERT INTO acting_opportunities SET (id, name, type) VALUES (?, ?, ?)"
  #   cursor = self._db.cursor()
  #   with self._db:
  #     cursor.execute(query, (opportunity.id, opportunity.name, opportunity.type.value))
  #     if actors:
  #       self.insert_opportunity_actors(opportunity.id, actors, cursor=cursor)


  # def insert_opportunity_actors(self,
  #     opportunity: int,
  #     actors: list[int],
  #     cursor = None):
  #   if cursor is None:
  #     cursor = self._db.cursor()

  #   query = "INSERT INTO acting_opportunities SET (actor, opportunity) VALUES (?, ?)"
  #   cursor.executemany(query, [
  #     (actor, opportunity.id) for actor in actors
  #   ])

