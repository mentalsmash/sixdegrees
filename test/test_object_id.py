from tmdbsimple.base import TMDB
from sixdegrees.core.tmdb import ObjectId, ObjectKind

def test_object_id_equals():
  def _test_object_kind(kind):
    a = ObjectId(kind, 0)

    assert a == a
    assert a.kind == kind
    assert a.n == 0
    assert isinstance(a.api, TMDB)

    # 
    b = ObjectId(kind, 0)
    assert a == b

    # 
    b = ObjectId(kind, 1)
    assert a != b

    for other_kind in ObjectKind:
      if other_kind == kind:
        continue

      # 
      a = ObjectId(kind, 0)
      b = ObjectId(other_kind, 0)
      assert a != b

  _test_object_kind(ObjectKind.PERSON)
  _test_object_kind(ObjectKind.MOVIE)
  _test_object_kind(ObjectKind.TV_SERIES)
  

