import unittest

from sdeck.i18n import set_language, tr
from sdeck.models import BUTTON_DECK_MODELS, match_deck_model


class DeckModelTests(unittest.TestCase):
    def test_catalog_layouts(self) -> None:
        self.assertEqual(BUTTON_DECK_MODELS["mini"]["key_count"], 6)
        self.assertEqual(BUTTON_DECK_MODELS["mk2"]["columns"], 5)
        self.assertEqual(BUTTON_DECK_MODELS["xl"]["rows"], 4)

    def test_specific_name_wins(self) -> None:
        self.assertEqual(match_deck_model("Stream Deck XL", 32, (4, 8)), "xl")
        self.assertEqual(match_deck_model("Stream Deck MK.2", 15, (3, 5)), "mk2")

    def test_dimensions_fallback(self) -> None:
        self.assertEqual(match_deck_model("Unknown", 6, (2, 3)), "mini")

    def test_neo_key_label_is_translatable(self) -> None:
        try:
            set_language("es")
            self.assertEqual(tr(BUTTON_DECK_MODELS["neo"]["name"]), "Stream Deck Neo (teclas)")
        finally:
            set_language("en")


if __name__ == "__main__":
    unittest.main()
