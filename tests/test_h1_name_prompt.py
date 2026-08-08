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

    def test_shell_has_future_identity_modules_without_warning_panel(self):
        self.assertIn('id="monSelect"', HTML)
        self.assertIn('id="identityHub"', HTML)
        self.assertIn('class="play-shell"', HTML)
        self.assertNotIn('class="danger"', HTML)
        self.assertNotIn('해킹 즉시', HTML)

    def test_visual_system_uses_simplified_neon_identity(self):
        self.assertIn('<span class="t-ball"', HTML)
        self.assertNotIn('clipPath id="ballClip"', HTML)
        self.assertNotIn('#ffd700', HTML)
        self.assertNotIn('#ffcf2e', HTML)
        self.assertNotIn('var(--yellow)', HTML)
        self.assertIn('--accent:#d94a38', HTML)
        self.assertIn('CHARACTER LANES', HTML)
        self.assertIn("const medals=['01','02','03'];", HTML)


if __name__ == "__main__":
    unittest.main()
