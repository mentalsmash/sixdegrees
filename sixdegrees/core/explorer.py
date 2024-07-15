from pathlib import Path
from typing import Iterable

from .database import Database
from .tmdb import ObjectKind

class Explorer:
  def __init__(self,
      db_file: Path | None = None,
      credits: "Iterable[ObjectKind] | None" = None) -> None:
    self.db = Database(db_file=db_file, credits=credits)

