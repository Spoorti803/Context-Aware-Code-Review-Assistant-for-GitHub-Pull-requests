import os
from tree_sitter import Language, Parser
import tree_sitter_python as tspython
import tree_sitter_javascript as tsjavascript

from app.github_client import get_file_lines, get_file_content, search_code

# tree-sitter 0.23.x — tree setter is a kind of parser used here. it is the library avialable
_PYTHON_LANG  = Language(tspython.language())
_JS_LANG      = Language(tsjavascript.language())

_PARSERS: dict[str, Parser] = {}


def _get_parser(filename: str) -> Parser | None:
    ext = os.path.splitext(filename)[1]
    lang_map = {
        ".py":  _PYTHON_LANG,
        ".js":  _JS_LANG,
        ".jsx": _JS_LANG,
        ".ts":  _JS_LANG,
        ".tsx": _JS_LANG,
    }
    lang = lang_map.get(ext)
    if lang is None:
        return None
    if ext not in _PARSERS:
        p = Parser()
        p.language = lang          # 0.23.x style
        _PARSERS[ext] = p
    return _PARSERS[ext]


def get_surrounding_lines(
    repo_full_name: str,
    ref: str,
    filename: str,
    changed_line: int,
    window: int = 20,
) -> list[str]:
    start = max(1, changed_line - window)
    end   = changed_line + window
    return get_file_lines(repo_full_name, ref, filename, start, end)


def extract_function(filename: str, source_lines: list[str], target_line: int) -> dict | None:
    parser = _get_parser(filename)
    if parser is None:
        return None

    source_text = "\n".join(source_lines).encode("utf-8")
    tree = parser.parse(source_text)

    FUNCTION_NODE_TYPES = {
        "function_definition",
        "function_declaration",
        "method_definition",
        "arrow_function",
    }

    best_node = None

    def walk(node):
        nonlocal best_node
        if node.type in FUNCTION_NODE_TYPES:
            fn_start = node.start_point[0] + 1
            fn_end   = node.end_point[0]   + 1
            if fn_start <= target_line <= fn_end:
                if best_node is None or (fn_end - fn_start) < (
                    best_node.end_point[0] - best_node.start_point[0]
                ):
                    best_node = node
        for child in node.children:
            walk(child)

    walk(tree.root_node)

    if best_node is None:
        return None

    fn_start = best_node.start_point[0]
    fn_end   = best_node.end_point[0]
    fn_lines = source_lines[fn_start : fn_end + 1]

    name = "unknown"
    for child in best_node.children:
        if child.type == "identifier":
            name = child.text.decode("utf-8")
            break

    return {
        "name":       name,
        "start_line": fn_start + 1,
        "end_line":   fn_end   + 1,
        "source":     "\n".join(fn_lines),
    }


def find_callers(
    repo_full_name: str,
    ref: str,
    function_info: dict | None,
    max_callers: int = 5,
) -> list[dict]:
    if function_info is None or function_info["name"] == "unknown":
        return []

    fn_name = function_info["name"]
    callers = []
    search_results = search_code(repo_full_name, fn_name)

    for result in search_results[:max_callers]:
        filename = result["filename"]
        try:
            source = get_file_content(repo_full_name, filename, ref)
        except Exception:
            continue

        parser = _get_parser(filename)
        if parser is None:
            continue

        tree  = parser.parse(source.encode("utf-8"))
        lines = source.splitlines()

        def find_calls(node, found):
            if node.type in {"call", "call_expression"}:
                callee_text = node.children[0].text.decode("utf-8") if node.children else ""
                if fn_name in callee_text:
                    line_num = node.start_point[0] + 1
                    snippet  = lines[node.start_point[0]] if node.start_point[0] < len(lines) else ""
                    found.append({"filename": filename, "line": line_num, "snippet": snippet})
            for child in node.children:
                find_calls(child, found)

        calls_in_file: list[dict] = []
        find_calls(tree.root_node, calls_in_file)
        callers.extend(calls_in_file[:2])

    return callers[:max_callers]


def rank_and_select(snippets: list[dict], max_snippets: int = 7) -> list[dict]:
    def score(s: dict) -> float:
        changed_count = len([l for l in s.get("changed_lines", []) if l["op"] in ("+", "-")])
        fn_len        = len(s["function_body"]["source"].splitlines()) if s.get("function_body") else 0
        caller_count  = len(s.get("callers", []))
        return changed_count * 3 + fn_len * 0.1 + caller_count * 2

    return sorted(snippets, key=score, reverse=True)[:max_snippets]
