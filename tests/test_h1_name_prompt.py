from pathlib import Path
import unittest


HTML = Path(__file__).resolve().parents[1].joinpath("index.html").read_text(encoding="utf-8")


class H1NamePromptTest(unittest.TestCase):
    def test_name_input_is_delayed_until_ranking_cta(self):
        self.assertIn('id="namePrompt"', HTML)
        self.assertIn('class="name-row hidden"', HTML)
        self.assertIn("showNamePrompt()", HTML)

        title_pos = HTML.index('class="title"')
        stats_pos = HTML.index('class="stats"')
        name_pos = HTML.index('id="namePrompt"')
        rank_pos = HTML.index('class="rank-panel"')

        self.assertLess(title_pos, stats_pos)
        self.assertLess(stats_pos, rank_pos)
        self.assertLess(rank_pos, name_pos)


if __name__ == "__main__":
    unittest.main()
