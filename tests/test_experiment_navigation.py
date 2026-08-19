import unittest
from unittest.mock import patch

from utils.ui import experiment_card


class ExperimentNavigationTestCase(unittest.TestCase):
    @patch("utils.ui.render_html")
    @patch("utils.ui.st.button", return_value=True)
    @patch("utils.ui.st.container")
    def test_clickable_card_uses_streamlit_button_without_navigation_link(
        self,
        mocked_container,
        mocked_button,
        mocked_render_html,
    ):
        clicked = experiment_card(
            title="Experiment A",
            snippet="Baseline observations",
            created_at="2026-08-19T10:00:00",
            chat_id=42,
        )

        self.assertTrue(clicked)
        mocked_container.assert_called_once_with(key="experiment_selector_42")
        mocked_button.assert_called_once()
        markup = mocked_render_html.call_args.args[0]
        self.assertIn('class="experiment-row"', markup)
        self.assertNotIn("href=", markup)
        self.assertNotIn("target=", markup)

    @patch("utils.ui.render_html")
    @patch("utils.ui.st.button")
    @patch("utils.ui.st.container")
    def test_noninteractive_card_remains_plain_markup(
        self,
        mocked_container,
        mocked_button,
        mocked_render_html,
    ):
        clicked = experiment_card(
            title="Experiment B",
            snippet="Summary context",
            created_at="2026-08-19T10:00:00",
            selected=True,
        )

        self.assertFalse(clicked)
        mocked_container.assert_not_called()
        mocked_button.assert_not_called()
        markup = mocked_render_html.call_args.args[0]
        self.assertIn('class="experiment-row selected"', markup)


if __name__ == "__main__":
    unittest.main()
