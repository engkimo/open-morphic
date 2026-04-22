"""Tests for TaskComplexityClassifier.requires_tools (Sprint 12.6)."""

from domain.services.task_complexity import TaskComplexityClassifier


class TestRequiresToolsJapanese:
    """Japanese keywords that indicate tool-requiring tasks."""

    def test_search(self) -> None:
        assert TaskComplexityClassifier.requires_tools("映画チケットを検索して")

    def test_find(self) -> None:
        assert TaskComplexityClassifier.requires_tools("一番安い映画館を探して")

    def test_investigate(self) -> None:
        assert TaskComplexityClassifier.requires_tools("天気を調べて")

    def test_ticket(self) -> None:
        assert TaskComplexityClassifier.requires_tools("ゴジュウジャーのチケットを取得して")

    def test_movie(self) -> None:
        assert TaskComplexityClassifier.requires_tools("映画の上映時間は？")

    def test_weather(self) -> None:
        assert TaskComplexityClassifier.requires_tools("明日の天気は？")

    def test_price(self) -> None:
        assert TaskComplexityClassifier.requires_tools("料金を比較")

    def test_latest(self) -> None:
        assert TaskComplexityClassifier.requires_tools("最新のニュースを教えて")


class TestRequiresToolsEnglish:
    """English keywords that indicate tool-requiring tasks."""

    def test_search(self) -> None:
        assert TaskComplexityClassifier.requires_tools("Search for movie tickets in Saitama")

    def test_find(self) -> None:
        assert TaskComplexityClassifier.requires_tools("Find the cheapest hotel in Tokyo")

    def test_look_up(self) -> None:
        assert TaskComplexityClassifier.requires_tools("Look up weather forecast")

    def test_fetch(self) -> None:
        assert TaskComplexityClassifier.requires_tools("Fetch the latest stock prices")

    def test_browse(self) -> None:
        assert TaskComplexityClassifier.requires_tools("Browse restaurant reviews")

    def test_latest(self) -> None:
        assert TaskComplexityClassifier.requires_tools("What is the latest news?")

    def test_this_week(self) -> None:
        assert TaskComplexityClassifier.requires_tools("Events this week in Tokyo")

    def test_real_time(self) -> None:
        assert TaskComplexityClassifier.requires_tools("Get real-time traffic data")

    def test_ticket(self) -> None:
        assert TaskComplexityClassifier.requires_tools("Buy a ticket for tonight's show")


class TestNotRequiringTools:
    """Tasks that should NOT require tools."""

    def test_simple_math(self) -> None:
        assert not TaskComplexityClassifier.requires_tools("1+1は？")

    def test_fibonacci(self) -> None:
        assert not TaskComplexityClassifier.requires_tools("Implement fibonacci in Python")

    def test_explain(self) -> None:
        assert not TaskComplexityClassifier.requires_tools("Explain quicksort algorithm")

    def test_write_function(self) -> None:
        assert not TaskComplexityClassifier.requires_tools("Write a hello world function")

    def test_refactor(self) -> None:
        assert not TaskComplexityClassifier.requires_tools("Refactor the auth module")

    def test_fix_bug(self) -> None:
        assert not TaskComplexityClassifier.requires_tools("Fix the typo in README")
