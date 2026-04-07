from common.persistence_schema import (
    CHECKPOINT_DDL_STATEMENTS,
    MEMORY_DDL_STATEMENTS,
    SESSION_DDL_STATEMENTS,
)


def _has_balanced_parentheses(sql: str) -> bool:
    depth = 0
    in_single_quote = False
    in_double_quote = False

    for index, char in enumerate(sql):
        previous = sql[index - 1] if index > 0 else ""
        if char == "'" and not in_double_quote and previous != "\\":
            in_single_quote = not in_single_quote
            continue
        if char == '"' and not in_single_quote and previous != "\\":
            in_double_quote = not in_double_quote
            continue
        if in_single_quote or in_double_quote:
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0 and not in_single_quote and not in_double_quote


def test_runtime_managed_ddl_statements_have_balanced_parentheses() -> None:
    for statement in (
        *CHECKPOINT_DDL_STATEMENTS,
        *SESSION_DDL_STATEMENTS,
        *MEMORY_DDL_STATEMENTS,
    ):
        assert _has_balanced_parentheses(statement), statement
