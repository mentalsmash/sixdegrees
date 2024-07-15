from enum import Enum
import tmdbsimple as tmdb

from .database import Database

class DatabaseObjectsCache:
  def __init__(self,
      db: Database) -> None:
    self.db = db
    self.actors: "dict[int, Actor]" = {}
    self.opportunities: "dict[int, Opportunity]" = {}


  def load_actor(self, id: int) -> "Actor":
    actor = self.actors.get(id)
    if actor is not None:
      return actor
    
    tmdb_actor = None
    actor_record = self.db.find_actor(id)
    if not actor_record:
      tmdb_actor = tmdb.People(id)
      tmdb_actor_info = tmdb_actor.info()
      actor = Actor(
        db=self,
        id=id,
        name=tmdb_actor_info["name"])
      self.insert_actor(actor)
    else:
      actor = Actor(
        db=self,
        id=id,
        name=actor_record.name)
    
    opp_ids = list(self.db.find_actor_opportunities(actor.id))
    if not opp_ids:
      if tmdb_actor is None:
        tmdb_actor = tmdb.People(actor.id)
      tmdb_opps = tmdb_actor.combined_credits()
      opportunities = [
        Opportunity(self,
          id=tmdb_opp["id"],
          name=tmdb_opp.get("name", tmdb_opp.get("original_title")),
          type=Opportunity.Type.parse_media_type(tmdb_opp["media_type"]))
        for tmdb_opp in tmdb_opps["cast"]
      ]
      for opp in opportunities:
        self.insert_opportunity(opp)
    else:
      opportunities = [
        self.load_opportunity(opp) for opp in opp_ids
      ]
    
    actor.opportunities = [opp.id for opp in opportunities]

    self.actors[id] = actor

    return actor

  def load_opportunity(self, id: int) -> "Opportunity":
    pass

  def insert_opportunity(self, opportunity: "Opportunity"):
    if opportunity.id not in self.opportunities:
      self.db.insert_opportunity(opportunity)
      self.opportunities[opportunity.id] = opportunity
    

  def insert_actor(self, actor: "Actor"):
    if actor.id not in self.actors:
      self.db.insert_actor(actor)
      self.actors[actor.id] = actor


class DatabaseObject:
  def __init__(self,
      db: DatabaseObjectsCache,
      id: int) -> None:
    self.db = db
    self.id = id

  def __eq__(self, value: object) -> bool:
    if not isinstance(value, self.__class__):
      return False
    return value.id == self.id

  def __hash__(self) -> int:
    return hash(self.id)


class Actor(DatabaseObject):
  def __init__(self,
      db: DatabaseObjectsCache,
      id: int,
      name: str) -> None:
    super().__init__(db, id)
    self.name = name

  @property
  def jobs(self) -> "list[Opportunity]":
    return []


class Opportunity:
  class Type(Enum):
    MOVIE = 1
    SERIES = 2
    EPISODE = 3

    @classmethod
    def parse_media_type(cls, media_type: str):
      return {
        "movie": Opportunity.Type.MOVIE,
        "tv": Opportunity.Type.SERIES,
      }[media_type.lower()]

  def __init__(self,
      db: DatabaseObjectsCache,
      id: int,
      name: str,
      type: "Opportunity.Type") -> None:
    super().__init__(db, id)
    self.name = name
    self.type = type


