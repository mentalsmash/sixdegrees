# Six Degrees

`6d` is a Python script to explore working connections between actors.

The script relies on [The Movie Database](https://www.themoviedb.org) to discover connections between actors.

## Installation

1. Install into a Python Virtual Environment with Python 3.9+:

   ```sh
   python3 -m venv ./venv
   
   . ./venv/bin/activate
   
   pip install git+https://github.com/mentalsmash/sixdegrees@master
   
   ```

2. Request an API key from The Movie Database.

## Usage

1. Load Python Virtual Environment:

   ```sh
   . ./venv/bin/activate
   ```

2. Export your TMDB API key as a variable:

   ```sh
   export TMDB_API_KEY="<key>"
   ```

3. Use command `6d` to access the included functionality:

   ```sh
   6d -h
   ```

### Who played that character?

- Search the main cast of a TV series:

  ```sh
  6d role -T "black books" bernard
  ```

- Search the cast of a specific episode of a TV series:

  ```sh
  6d role -T seinfeld -e 4x11 marla
  ```

- Search the cast of a specific season of TV series:

  ```sh
  6d role -S "the office" -s 1 roy
  ```

- Search the cast of all seasons of a TV series (i.e. download more detailed season information):

  ```sh
  6d role -T "community" -t pierce
  ```

- Show the main cast of a TV series:

  ```sh
  6d role -T "the office"
  ```

- Show the cast of a specific episode of a TV series:

  ```sh
  6d role -T "the office" -e s01e01
  ```

- Show the cast of a specific season of a TV series:

  ```sh
  6d role -T "the office" -s 1
  ```

### Whas that actor in that?

- Search an actor's credit for a specific TV series:

  ```sh
  6d played "bryan cranston" -T "murder she wrote"
  ```

- Check if an actor playing a character in a TV series episode was in a movie:

  ```sh
  6d played $(6d role -T "black books" bernard) -M "shaun of the dead"
  ```

- Show all roles played by an actor:

  ```sh
  6d played "bryan cranston"
  ```

