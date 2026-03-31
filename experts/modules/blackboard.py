"""blackboard.py — 专家间共享的黑板（简单 key-value store）"""

class Blackboard:
    def __init__(self):
        self._store: dict = {}

    def write(self, agent: str, round_num: int, key: str, value):
        self._store[(agent, round_num, key)] = value

    def read(self, agent: str, round_num: int, key: str):
        return self._store.get((agent, round_num, key))

    def all(self) -> dict:
        return dict(self._store)
