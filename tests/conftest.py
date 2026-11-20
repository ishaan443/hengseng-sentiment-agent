from pathlib import Path
import pytest
import pandas as pd

from hengseng.common import read_json, read_jsonl
from hengseng.demo import generate
from hengseng.sentiment import LexiconScorer, score_posts

ROOT = Path(__file__).parents[1]


@pytest.fixture(scope="session")
def assets():
    return read_json(ROOT / "config/assets.json")


@pytest.fixture(scope="session")
def synthetic(tmp_path_factory, assets):
    directory = tmp_path_factory.mktemp("demo")
    end = generate(assets, directory, end="2026-03-31")
    prices = pd.read_csv(directory / "prices.csv")
    posts = score_posts(read_jsonl(directory / "posts.jsonl"), LexiconScorer())
    return directory, end, prices, posts
