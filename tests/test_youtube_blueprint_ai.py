import unittest
from unittest.mock import patch
from backend.youtube_blueprint_ai import suggest_youtube_blueprint
from backend.text_generation import ProviderResult


class TestYoutubeBlueprintAI(unittest.TestCase):
    @patch("backend.youtube_blueprint_ai.generate_text")
    def test_suggest_youtube_blueprint_parses_json_correctly(self, mock_generate_text):
        mock_payload = """
        {
            "format": "cinematic_storytelling",
            "market": "United States",
            "language": "Native US English",
            "micro_niche": "Dark Psychology in Historical Politics",
            "core_audience": "Curious adults interested in unrevealed history",
            "channel_promise": "Rigorous evidence and dramatic visual narrative",
            "demand_evidence": "Over 500k monthly search volume across related terms",
            "competitor_gap": "Competitors use robotic voiceovers and lack primary sources",
            "original_angle": "Focusing on declassified archives and psychological letters",
            "hook_cold_open": "In 1983, one man made a decision that the government tried to erase.",
            "macro_open_loop": "Why was this secret hidden for 40 years?",
            "payoff_next_view": "The complete declassified transcript revealed.",
            "brand_architecture": "cinematic_deep_dive",
            "colors": "Navy + Muted Gold",
            "font": "Montserrat",
            "main_keyword": "cold war secret submarine",
            "relevant_keywords": "submarine history, 1983 incident, declassified",
            "long_tail_intent": "what really happened in 1983 soviet incident",
            "sources_and_licensing": "National Archives, Public Domain Footage",
            "editorial_thesis": "History is shaped by individual moral courage under extreme pressure",
            "content_moat": "Deep primary source research combined with cinematic scene pacing",
            "fleet_governance": "Lead Researcher, Script Editor, Fact Checker",
            "production_cost": 45,
            "ai_disclosure": "review_required",
            "human_contribution": "Original archival research and commentary",
            "localization_qa": "US idioms and terminology verified",
            "audio_qa": "Layered room tone, contextual foley, voice at -14 LUFS",
            "continuity_ledger": "Submarine bridge setup, lighting low-key red and amber",
            "loop_ledger": "Loop 1 opened at 0:00, resolved at 8:30",
            "risk_register": "No copyright risk on government documents"
        }
        """
        mock_generate_text.return_value = ProviderResult(
            text=mock_payload, provider="mock", model="mock-model"
        )

        result = suggest_youtube_blueprint(
            topic="1983 Soviet Submarine",
            format_type="cinematic_storytelling",
            market="United States",
            language="Native US English",
        )

        self.assertEqual(result["micro_niche"], "Dark Psychology in Historical Politics")
        self.assertEqual(result["main_keyword"], "cold war secret submarine")
        self.assertEqual(result["brand_architecture"], "cinematic_deep_dive")
        self.assertEqual(result["production_cost"], 45)


if __name__ == "__main__":
    unittest.main()
