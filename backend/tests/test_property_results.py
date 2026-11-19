import unittest

from app.llm import (
    _deduplicate_property_sections, _ensure_specific_property_section,
    _prior_user_messages,
)
from app.vocab import (
    extract_area_display, extract_bedroom_options, mentioned_property_titles,
    property_key,
)


class PropertyResultTests(unittest.TestCase):
    def test_extracts_labeled_area_ranges_and_keeps_source_units(self):
        self.assertEqual(
            extract_area_display({}, "AREA (SQFT)\n764 - 7,720"),
            "764 to 7,720 SQFT",
        )
        self.assertEqual(
            extract_area_display({}, "Area BAU (SQFT)\n2899 to 4048"),
            "2,899 to 4,048 SQFT",
        )
        self.assertEqual(
            extract_area_display({"area (sqm)": "109 to 722"}, ""),
            "109 to 722 SQM",
        )

    def test_extracts_all_explicit_bedroom_layouts(self):
        self.assertEqual(
            extract_bedroom_options("Unit Type 1, 2 & 3-bedrooms"),
            [1, 2, 3],
        )
        self.assertEqual(
            extract_bedroom_options("Elegant 1-2-3-4 bedroom apartments"),
            [1, 2, 3, 4],
        )
        self.assertEqual(extract_bedroom_options("2-4 bedroom apartments"), [])
        self.assertEqual(extract_bedroom_options("Apartment with 3 bedrooms"), [])

    def test_detects_named_property_but_not_broad_bedroom_search(self):
        titles = [
            "Sea View Residences & Luxury Apartments in Doha, Qatar - Les Vagues | DarGlobal",
            "Apartment 375 SQM with 4 Bedrooms",
        ]
        self.assertEqual(
            mentioned_property_titles(
                "Does Les Vagues have 4-bedroom layouts?", titles
            ),
            {titles[0]},
        )
        self.assertEqual(
            mentioned_property_titles("Show me Wasalt listings with 4 bedrooms", titles),
            set(),
        )

    def test_duplicate_wasalt_ads_with_same_indexed_facts_share_a_key(self):
        header = (
            "Source: WASALT | Title: Apartment 600 SQM with 3 Bedrooms | "
            "Location: Al Rabbwah, Jeddah, Saudi Arabia | Type: apartment | "
            "Bedrooms: 3 | Price: 367,000 SAR | Status: Active"
        )
        self.assertEqual(
            property_key("wasalt", "https://wasalt.sa/listing/1", header),
            property_key("wasalt", "https://wasalt.sa/listing/2", header),
        )

    def test_different_wasalt_facts_and_other_sources_remain_distinct(self):
        first = "Title: Apartment | Location: Jeddah | Type: apartment | Bedrooms: 3 | Price: 367 SAR"
        second = first.replace("367 SAR", "368 SAR")
        self.assertNotEqual(
            property_key("wasalt", "/listing/1", first),
            property_key("wasalt", "/listing/2", second),
        )
        self.assertNotEqual(
            property_key("darglobal", "/listing/1", first),
            property_key("darglobal", "/listing/2", first),
        )

    def test_unformatted_specific_answer_gets_grounded_property_section(self):
        context = [(
            "Source: DAR GLOBAL | Title: Pagani Penthouse | Location: Dubai, UAE | "
            "Type: penthouse | Price: Not stated | Status: Sold Out\n\n"
            "Spanning 14,768 sqft, the residence includes advanced domotics.",
            "Pagani Penthouse", "https://example.test/pagani", "darglobal",
        )]
        result = _ensure_specific_property_section(
            "The penthouse offers advanced domotics.",
            "What amenities are offered at Pagani Penthouse in Dubai?",
            context,
        )
        self.assertIn("The penthouse offers advanced domotics.", result)
        self.assertIn("## Pagani Penthouse", result)
        self.assertIn("- **Area:** 14,768 SQFT", result)
        self.assertIn("- **Amenities:** Not stated", result)
        self.assertIn("- **Source:** https://example.test/pagani", result)

    def test_existing_property_section_is_not_modified(self):
        answer = "## Pagani Penthouse\n- **Price:** Not stated"
        self.assertEqual(
            _ensure_specific_property_section(answer, "Pagani Penthouse", []),
            answer,
        )

    def test_duplicate_response_sections_with_same_source_are_removed(self):
        answer = (
            "Intro\n\n"
            "## First listing\n- **Source:** https://wasalt.sa/property/one\n\n"
            "## Repeated listing\n- **Source:** https://wasalt.sa/property/one/\n\n"
            "## Another listing\n- **Source:** https://wasalt.sa/property/two"
        )
        result = _deduplicate_property_sections(answer)
        self.assertIn("## First listing", result)
        self.assertNotIn("## Repeated listing", result)
        self.assertIn("## Another listing", result)

    def test_prior_assistant_facts_are_not_reused_as_current_context(self):
        history = [
            {"role": "user", "content": "What layouts does Les Vagues offer?"},
            {"role": "assistant", "content": "Bedrooms: 1, 2, 3"},
            {"role": "user", "content": "Does it have four bedrooms?"},
        ]
        self.assertEqual(
            _prior_user_messages("Does Les Vagues have four bedrooms?", history),
            [],
        )
        self.assertEqual(
            _prior_user_messages("What about its price?", history),
            [history[0], history[2]],
        )


if __name__ == "__main__":
    unittest.main()
