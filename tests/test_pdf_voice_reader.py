"""Tests for PDF voice reader helpers that do not need a GUI window."""

import unittest

from simple_project.pdf_voice_reader import DictionaryClient, normalize_word


class PdfVoiceReaderTests(unittest.TestCase):
    def test_normalize_word_picks_first_dictionary_word(self) -> None:
        self.assertEqual(normalize_word("  Reading, aloud!"), "reading")

    def test_format_definition_includes_part_of_speech_and_source(self) -> None:
        payload = [
            {
                "word": "test",
                "phonetic": "/test/",
                "meanings": [
                    {
                        "partOfSpeech": "noun",
                        "definitions": [
                            {
                                "definition": "A procedure for checking quality.",
                                "example": "The student passed the test.",
                            }
                        ],
                    }
                ],
            }
        ]

        definition = DictionaryClient._format_definition(payload, "test")

        self.assertIn("Test", definition)
        self.assertIn("/test/", definition)
        self.assertIn("1. (noun) A procedure for checking quality.", definition)
        self.assertIn("Example: The student passed the test.", definition)
        self.assertIn("Source: Free Dictionary API", definition)


if __name__ == "__main__":
    unittest.main()
