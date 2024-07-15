import sys
import subprocess
import re
import traceback
from typing import Callable, Iterable, TextIO

from .log import Logger as log

_ScriptNoninteractiveRequired = not sys.stdin.isatty() or not sys.stdout.isatty()
_ScriptNoninteractive = False

###############################################################################
# Filter a list using fzf
###############################################################################
def fzf_tab_separated_results_parser(fields_count: int) -> "Callable[[str], list[str] | None]":
  # Parse a string of fields separated by tabs.
  assert fields_count >= 1
  parse_re = re.compile(
    "".join(("^", *(r"([^\t]+)[\t]+" for _ in range(fields_count - 1)), r"(.*)", "$"))
  )
  def _parser(line: str) -> object | None:
    try:
      fields = parse_re.findall(line)
      fields = fields[0]
      return list(fields)
    except Exception:
      log.error("failed to parse result line: '{}'", line)
      traceback.print_exc()
      return None
  return _parser


def fzf_filter(
  filter: str | None = None,
  inputs: list | None = None,
  keep_stdin_open: bool = False,
  prompt: str | None = None,
  noninteractive: bool = False,
  result_parser: "Callable[[str], object | None] | None" = None
) -> subprocess.Popen | Iterable[object]:
  noninteractive = noninteractive or _ScriptNoninteractive
  if noninteractive:
    filter_arg = "--filter"
  else:
    filter_arg = "--query"

  if filter is None:
    filter = ""

  if prompt is None:
    prompt = ""
  # if prompt[-2:] != "> ":
  prompt += " (TAB: select, ENTER: confirm/select + exit, ESC: exit)> "

  fzf_cmd = [
    "fzf",
    "-0",
    "--tac",
    "--no-sort",
    "--multi",
    "--bind",
    "ctrl-a:select-all,ctrl-d:deselect-all,ctrl-t:toggle-all",
    "--prompt",
    prompt,
    filter_arg,
    filter]
  log.exec_command(fzf_cmd)
  fzf = subprocess.Popen(fzf_cmd, stdout=subprocess.PIPE, stdin=subprocess.PIPE)
  if inputs:
    for line in inputs:
      line = str(line).strip()
      fzf.stdin.write(line.encode())
      fzf.stdin.write("\n".encode())
    if not keep_stdin_open:
      fzf.stdin.close()

  def _read_and_parse(input_stream: TextIO) -> list[object]:
    return [
      result
      for line in input_stream.readlines()
      for sline in [line.decode().strip()]
      if sline
      for result in [result_parser(sline)]
      if result is not None
    ]

  if result_parser:
    return _read_and_parse(fzf.stdout)
  else:
    return fzf


def fzf_global_interactive(interactive: bool) -> None:
  if interactive and _ScriptNoninteractiveRequired:
    raise RuntimeError("interactive fzf requires a terminal")
  global _ScriptNoninteractive
  _ScriptNoninteractive = not interactive


def fzf_interactive_supported() -> bool:
  return not _ScriptNoninteractiveRequired
