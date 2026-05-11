from todo_app import Todo, list_todos


def test_list_todos_returns_all_items():
    todos = [
        Todo(id=1, title="Write spec", completed=True),
        Todo(id=2, title="Build CLI", completed=False),
    ]

    assert list_todos(todos) == todos

