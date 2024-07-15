-------------------------------------------------------------------------------
-- movies --
-------------------------------------------------------------------------------
CREATE TABLE movies (
  id INTEGER PRIMARY KEY,
  metadata TEXT NOT NULL,
  explored_depth INTEGER DEFAULT 0);

-------------------------------------------------------------------------------
-- tv_series --
-------------------------------------------------------------------------------
CREATE TABLE tv_series (
  id INTEGER PRIMARY KEY,
  metadata TEXT NOT NULL,
  explored_depth INTEGER DEFAULT 0);

-------------------------------------------------------------------------------
-- people --
-------------------------------------------------------------------------------
CREATE TABLE people (
  id INTEGER PRIMARY KEY,
  metadata TEXT NOT NULL,
  explored_depth INTEGER DEFAULT 0);

-------------------------------------------------------------------------------
-- movie_credits --
-------------------------------------------------------------------------------
CREATE TABLE movie_credits (
  actor INTEGER NOT NULL,
  job INTEGER NOT NULL,
  FOREIGN KEY(actor) REFERENCES actors(id),
  FOREIGN KEY(job) REFERENCES movies(id),
  PRIMARY KEY(actor, job));

-------------------------------------------------------------------------------
-- tv_credits --
-------------------------------------------------------------------------------
CREATE TABLE tv_credits (
  actor INTEGER NOT NULL,
  job INTEGER NOT NULL,
  FOREIGN KEY(actor) REFERENCES actors(id),
  FOREIGN KEY(job) REFERENCES tv_series(id),
  PRIMARY KEY(actor, job));

-------------------------------------------------------------------------------
-- graph_tv --
-------------------------------------------------------------------------------
CREATE TABLE graph_tv (
  a INTEGER NOT NULL,
  b INTEGER NOT NULL CHECK(a != b AND a <= b),
  e INTEGER NOT NULL,
  FOREIGN KEY(a) REFERENCES actors(id),
  FOREIGN KEY(b) REFERENCES actors(id),
  FOREIGN KEY(e) REFERENCES tv_series(id),
  PRIMARY KEY(a, b, e));

-------------------------------------------------------------------------------
-- graph_movie --
-------------------------------------------------------------------------------
CREATE TABLE graph_movie (
  a INTEGER NOT NULL,
  b INTEGER NOT NULL CHECK(a != b AND a <= b),
  e INTEGER NOT NULL,
  FOREIGN KEY(a) REFERENCES actors(id),
  FOREIGN KEY(b) REFERENCES actors(id),
  FOREIGN KEY(e) REFERENCES movies(id),
  PRIMARY KEY(a, b, e));

