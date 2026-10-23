import sys
import json
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).parents[1] / "modules" / "lambda" / "opportunity-digest"))

import handler


def scoring_payload(procurement_mode="other", procurement_category="other", actionable=True, company_overrides=None):
    companies = {
        company: {
            "capability_relevance": 0,
            "pursuit_fit": 0,
            "existing_capability": "unknown",
            "would_require_new_core_product": "unknown",
            "prime_or_sub": "unknown",
            "why_it_fits": [],
            "blockers": [],
            "recommended_angle": "",
            "rejection_reason": None,
        }
        for company in handler.COMPANY_PROFILES
    }
    for company, values in (company_overrides or {}).items():
        companies[company].update(values)
    return {
        "actionable": actionable,
        "actionability_reason": "Current open response window" if actionable else "Awarded or closed",
        "procurement_category": procurement_category,
        "buyer_need": "Buyer description",
        "procurement_mode": procurement_mode,
        "required_deliverable": "Specific requested deliverable",
        "companies": companies,
    }


class OpportunityDigestTests(unittest.TestCase):
    def test_expired_and_inactive_opportunities_are_filtered(self):
        today = date(2026, 10, 2)
        self.assertTrue(handler.is_expired({"deadline": "2026-10-01"}, today))
        self.assertFalse(handler.is_expired({"deadline": "2026-10-02"}, today))
        self.assertFalse(handler.is_expired({"deadline": "2026-10-03"}, today))
        self.assertFalse(handler.is_open({"deadline": "2026-10-05", "active": "No"}, today))
        self.assertEqual(
            handler.deduplicate_opportunities([
                {"id": "old", "deadline": "2026-10-01", "active": "Yes"},
                {"id": "closed", "deadline": "2026-10-05", "active": "No"},
                {"id": "awarded", "title": "CMPro Software and Support Award Notice", "active": "Yes"},
                {"id": "open", "deadline": "2026-10-05", "active": "Yes"},
            ]),
            [{"id": "open", "deadline": "2026-10-05", "active": "Yes", "search_companies": []}],
        )

    def test_scoring_response_parses_and_validates_json(self):
        response = {"choices": [{"message": {"content": json.dumps(scoring_payload(
            procurement_mode="custom_development",
            procurement_category="custom_software",
            company_overrides={"boring": {
                "capability_relevance": 92,
                "pursuit_fit": 87,
                "existing_capability": False,
                "would_require_new_core_product": False,
                "prime_or_sub": "prime",
                "why_it_fits": ["Buyer needs a custom web application"],
            }},
        ))}}]}
        result = handler.parse_scoring_response(response)
        self.assertEqual(result["companies"]["boring"]["capability_relevance"], 92)
        self.assertEqual(result["companies"]["boring"]["pursuit_fit"], 87)
        self.assertEqual(result["companies"]["boring"]["why_it_fits"], ["Buyer needs a custom web application"])
        self.assertEqual(result["buyer_need"], "Buyer description")
        with self.assertRaises(ValueError):
            invalid = scoring_payload()
            invalid["procurement_mode"] = "not_a_real_mode"
            handler.parse_scoring_response(invalid)

    def test_score_threshold_uses_pursuit_fit_not_capability_relevance(self):
        custom_portal = handler.parse_scoring_response(scoring_payload(
            procurement_mode="custom_development",
            procurement_category="custom_software",
            company_overrides={"boring": {"capability_relevance": 96, "pursuit_fit": 91}},
        ))
        self.assertTrue(handler.worth_emailing(custom_portal, "boring", 80))

        army_simulation = handler.parse_scoring_response(scoring_payload(
            procurement_mode="prototype_existing_technology",
            company_overrides={"boring": {
                "capability_relevance": 75,
                "pursuit_fit": 88,
                "existing_capability": False,
                "would_require_new_core_product": True,
            }},
        ))
        self.assertEqual(army_simulation["companies"]["boring"]["pursuit_fit"], 64)
        self.assertFalse(handler.worth_emailing(army_simulation, "boring", 80))

        part_purchase = handler.parse_scoring_response(scoring_payload(
            procurement_mode="commodity_purchase",
            procurement_category="hardware_supply",
            company_overrides={"farawatt": {"capability_relevance": 95, "pursuit_fit": 99}},
        ))
        self.assertFalse(handler.worth_emailing(part_purchase, "farawatt", 80))

        weak_pursuit = handler.parse_scoring_response(scoring_payload(
            procurement_mode="engineering_services",
            procurement_category="professional_services",
            company_overrides={"farawatt": {"capability_relevance": 99, "pursuit_fit": 72}},
        ))
        self.assertFalse(handler.worth_emailing(weak_pursuit, "farawatt", 80))
        self.assertTrue(handler.worth_reviewing(weak_pursuit, "farawatt"))

    def test_regression_fit_examples_are_assessed_independently(self):
        county_portal = handler.parse_scoring_response(scoring_payload(
            procurement_mode="custom_development",
            procurement_category="custom_software",
            company_overrides={
                "boring": {"capability_relevance": 97, "pursuit_fit": 92, "existing_capability": False},
                "vivesound": {"capability_relevance": 20, "pursuit_fit": 5},
                "farawatt": {"capability_relevance": 0, "pursuit_fit": 0},
            },
        ))
        self.assertTrue(handler.worth_emailing(county_portal, "boring", 80))
        self.assertFalse(handler.worth_emailing(county_portal, "vivesound", 80))

        voice = handler.parse_scoring_response(scoring_payload(
            procurement_mode="prototype_existing_technology",
            procurement_category="professional_services",
            company_overrides={
                "vivesound": {"capability_relevance": 98, "pursuit_fit": 93, "existing_capability": True},
            },
        ))
        self.assertTrue(handler.worth_emailing(voice, "vivesound", 80))

        arc_flash = handler.parse_scoring_response(scoring_payload(
            procurement_mode="engineering_services",
            procurement_category="professional_services",
            company_overrides={
                "farawatt": {"capability_relevance": 100, "pursuit_fit": 95, "existing_capability": True},
            },
        ))
        self.assertTrue(handler.worth_emailing(arc_flash, "farawatt", 80))

        arcgis_license = handler.parse_scoring_response(scoring_payload(
            procurement_mode="software_license",
            procurement_category="software_license",
            company_overrides={
                "boring": {"capability_relevance": 70, "pursuit_fit": 90, "existing_capability": False},
            },
        ))
        self.assertFalse(handler.worth_emailing(arcgis_license, "boring", 80))

        army_product = handler.parse_scoring_response(scoring_payload(
            procurement_mode="existing_product",
            procurement_category="other",
            company_overrides={
                "boring": {"capability_relevance": 75, "pursuit_fit": 95, "existing_capability": True},
            },
        ))
        self.assertFalse(handler.worth_emailing(army_product, "boring", 80))

    def test_duplicate_search_results_collapse_and_previously_sent_are_removed(self):
        first = {"id": "same", "title": "Power design", "search_companies": ["farawatt"], "description": "short"}
        duplicate = {"id": "same", "title": "Power design", "search_companies": ["boring"], "description": "more detail"}
        unique = handler.deduplicate_opportunities([first, duplicate])
        self.assertEqual(len(unique), 1)
        self.assertCountEqual(unique[0]["search_companies"], ["farawatt", "boring"])
        self.assertEqual(unique[0]["description"], "more detail")

        collection = Mock()
        collection.find.return_value = [{"_id": "same|farawatt", "company": "farawatt"}]
        new_items = handler.filter_unemailed([unique[0], {"id": "new"}], collection)
        self.assertEqual(len(new_items), 2)
        self.assertEqual(new_items[0]["emailed_companies"], ["farawatt"])
        self.assertEqual(new_items[1]["emailed_companies"], [])
        self.assertFalse(handler.worth_emailing(
            scoring_payload(company_overrides={"farawatt": {"pursuit_fit": 95}}),
            "farawatt",
            80,
            new_items[0]["emailed_companies"],
        ))
        self.assertTrue(handler.worth_emailing(
            scoring_payload(company_overrides={"boring": {"pursuit_fit": 95}}),
            "boring",
            80,
            new_items[0]["emailed_companies"],
        ))

    def test_digest_format_includes_known_details_and_omits_unknown_values(self):
        digest = handler.format_digest([{
            "company": "vivesound",
            "score": 92,
            "pursuit_fit": 92,
            "capability_relevance": 97,
            "buyer_need": "Real-time voice processing over lossy networks",
            "procurement_mode": "integration_services",
            "required_deliverable": "Integrate a low-latency voice processing SDK",
            "title": "Resilient Voice Communications",
            "organization": "US Air Force",
            "deadline": "Oct 28, 2026",
            "value": "",
            "type": "Prototype",
            "why_it_fits": ["Real-time voice over unreliable networks"],
            "concerns": ["Cybersecurity requirements need review"],
            "prime_or_sub": "sub",
            "recommended_angle": "Use Roc for resilient transport.",
            "url": "https://example.test/opportunity",
            "source": "Private RFP",
            "actionability_reason": "Open response deadline and explicit audio software integration scope",
        }])
        self.assertIn("VIVESOUND", digest)
        self.assertIn("92/100", digest)
        self.assertIn("Due: Oct 28, 2026", digest)
        self.assertNotIn("Value:", digest)
        self.assertIn("Likely role: sub", digest)
        self.assertIn("Source: Private RFP", digest)
        self.assertIn("Mode: integration services", digest)
        self.assertIn("Capability relevance: 97/100", digest)
        self.assertIn("Pursuit fit: 92/100", digest)
        self.assertIn("Buyer need: Real-time voice processing", digest)
        self.assertIn("https://example.test/opportunity", digest)

    def test_public_web_queries_include_local_regions_and_other_call_types(self):
        self.assertTrue(any("Maryland" in query for query in handler.WEB_SEARCH_QUERIES["vivesound"]))
        self.assertTrue(any("North Carolina" in query for query in handler.WEB_SEARCH_QUERIES["farawatt"]))
        self.assertTrue(any("North Carolina" in query and "Maryland" in query for query in handler.WEB_SEARCH_QUERIES["boring"]))
        self.assertTrue(any("STTR" in modifier for modifier in handler.SEARCH_QUERY_MODIFIERS))
        self.assertTrue(any("open call" in modifier for modifier in handler.SEARCH_QUERY_MODIFIERS))

    def test_retrieval_ranks_relevance_without_using_rank_as_rejection(self):
        commodity = {
            "id": "part",
            "title": "Electrical cable, power supply",
            "search_companies": ["farawatt"],
        }
        study = {
            "id": "study",
            "title": "Municipal arc-flash and coordination study",
            "search_companies": ["farawatt"],
        }
        self.assertGreater(handler.retrieval_score(study, "farawatt"), handler.retrieval_score(commodity, "farawatt"))
        self.assertEqual(handler.select_candidates([commodity, study], max_per_company=1), [study])
        self.assertIn(commodity, handler.select_candidates([commodity], max_per_company=1))

    def test_clinical_audiology_equipment_is_not_a_vivesound_match(self):
        assessment = handler.parse_scoring_response(scoring_payload(
            procurement_mode="equipment_purchase",
            procurement_category="hardware_supply",
            company_overrides={
                "vivesound": {
                    "capability_relevance": 70,
                    "pursuit_fit": 0,
                    "existing_capability": False,
                    "would_require_new_core_product": True,
                    "blockers": ["Buyer is purchasing clinical audiology equipment, not audio software"],
                    "rejection_reason": "Physical clinical devices are not ViveSound's offering",
                },
            },
        ))
        self.assertFalse(handler.worth_emailing(assessment, "vivesound", 80))
        self.assertEqual(assessment["companies"]["vivesound"]["capability_relevance"], 70)

    def test_award_notices_are_not_open_opportunities(self):
        self.assertFalse(handler.is_open({"title": "CMPro Software and Support Award Notice"}))
        self.assertFalse(handler.is_open({"type": "Award Notice", "active": "Yes"}))
        self.assertTrue(handler.is_open({"title": "Open software development RFP", "active": "Yes"}))

    def test_funnel_diagnostics_log_counts_and_bounded_samples_without_descriptions(self):
        diagnostics = handler.new_funnel_diagnostics()
        samples = {company: [] for company in handler.COMPANY_PROFILES}
        diagnostics["vivesound"]["raw_sam"] = 84
        opportunity = {
            "title": "Audiometer procurement",
            "source": "SAM.gov",
            "search_companies": ["vivesound"],
            "description": "private solicitation text that must not appear in the diagnostic log",
        }
        for _ in range(5):
            handler._sample_rejection(samples, opportunity, "medical_equipment")
        with self.assertLogs(handler.LOGGER, level="INFO") as captured:
            handler.log_funnel_diagnostics(diagnostics, samples)
        output = "\n".join(captured.output)
        self.assertIn('"raw_sam": 84', output)
        self.assertIn('"reason": "medical_equipment"', output)
        self.assertEqual(len(samples["vivesound"]), 3)
        self.assertNotIn("private solicitation text", output)

    def test_sample_pipeline_counts_where_candidates_are_removed(self):
        sam_results = [
            {
                "id": "portal", "title": "County permitting portal development solicitation",
                "description": "Develop a new web portal.", "type": "Solicitation", "active": "Yes",
                "search_companies": ["boring"], "source": "SAM.gov",
            },
            {
                "id": "award", "title": "ArcGIS Software and Support Award Notice",
                "type": "Award Notice", "active": "Yes", "search_companies": ["boring"], "source": "SAM.gov",
            },
            {
                "id": "study", "title": "Municipal arc flash and coordination study",
                "description": "Engineering consultant to perform short circuit studies.",
                "type": "RFP", "active": "Yes", "search_companies": ["farawatt"], "source": "SAM.gov",
            },
        ]
        web_results = [
            {
                "id": "portal", "title": "County permitting portal development solicitation",
                "description": "Develop a new administrative web portal with REST APIs.",
                "active": "Yes", "search_companies": ["boring"], "source": "county.gov",
            },
            {
                "id": "audio", "title": "Low-latency voice processing opportunity",
                "description": "Real-time speech processing over lossy IP networks.",
                "active": "Yes", "search_companies": ["vivesound"], "source": "private-rfp.test",
            },
            {
                "id": "cable", "title": "CABLE, POWER, ELECTRICAL",
                "active": "Yes", "search_companies": ["farawatt"], "source": "vendor.test",
            },
            {
                "id": "possible", "title": "County electrical engineering consulting task order",
                "description": "Consulting for a power distribution assessment.",
                "active": "Yes", "search_companies": ["farawatt"], "source": "county.gov",
            },
        ]
        diagnostics = handler.new_funnel_diagnostics()
        rejection_samples = {company: [] for company in handler.COMPANY_PROFILES}
        candidates = handler.prepare_ai_candidates(sam_results, web_results, diagnostics, rejection_samples, 20)
        handler.count_selected_for_ai(diagnostics, len(candidates))

        strong_matches = []
        possible_matches = []
        sample_scores = {
            "portal": ("boring", 90, "custom_development", "custom_software"),
            "audio": ("vivesound", 92, "prototype_existing_technology", "professional_services"),
            "study": ("farawatt", 95, "engineering_services", "professional_services"),
            "possible": ("farawatt", 72, "engineering_services", "professional_services"),
        }
        for opportunity in candidates:
            company, score, mode, category = sample_scores[opportunity["id"]]
            assessment = handler.parse_scoring_response(scoring_payload(
                procurement_mode=mode,
                procurement_category=category,
                company_overrides={company: {"pursuit_fit": score, "capability_relevance": min(99, score + 4)}},
            ))
            matches, possibles = handler.evaluate_assessment(opportunity, assessment, diagnostics, rejection_samples, 80)
            strong_matches.extend(matches)
            possible_matches.extend(possibles)
        handler.count_emailed_matches(diagnostics, strong_matches)
        for match in possible_matches:
            diagnostics[match["company"]]["possible"] += 1

        self.assertEqual(len(candidates), 4)
        self.assertEqual(len(strong_matches), 3)
        self.assertEqual(len(possible_matches), 1)
        self.assertEqual(diagnostics["boring"]["raw_sam"], 2)
        self.assertEqual(diagnostics["boring"]["raw_web"], 1)
        self.assertEqual(diagnostics["boring"]["after_dedupe"], 2)
        self.assertEqual(diagnostics["boring"]["rejected_closed"], 1)
        self.assertEqual(diagnostics["boring"]["before_candidate_limit"], 1)
        self.assertEqual(diagnostics["boring"]["selected_for_ai"], 4)
        self.assertEqual(diagnostics["boring"]["emailed"], 1)
        self.assertEqual(diagnostics["vivesound"]["raw_web"], 1)
        self.assertEqual(diagnostics["vivesound"]["score_ge80"], 1)
        self.assertEqual(diagnostics["vivesound"]["score_lt65"], 3)
        self.assertEqual(diagnostics["farawatt"]["rejected_deterministic"], 1)
        self.assertEqual(diagnostics["farawatt"]["before_candidate_limit"], 2)
        self.assertEqual(diagnostics["farawatt"]["ranked_candidates"], 2)
        self.assertEqual(diagnostics["farawatt"]["score_ge80"], 1)
        self.assertEqual(diagnostics["farawatt"]["score_65_79"], 1)
        self.assertEqual(diagnostics["farawatt"]["emailed"], 1)
        self.assertEqual(diagnostics["vivesound"]["emailed"], 1)

    @patch("handler.http_json_request")
    def test_sam_search_uses_official_api_parameters(self, request):
        request.return_value = {"opportunitiesData": [{
            "noticeId": "notice-1",
            "title": "Audio communications system",
            "fullParentPathName": "Department of Defense",
            "responseDeadLine": "2026-12-01",
            "uiLink": "https://sam.gov/opp/notice-1/view",
        }]}
        results = handler.search_sam("sam-secret", 7)
        self.assertGreaterEqual(request.call_count, 3)
        query = parse_qs(urlsplit(request.call_args_list[0].args[0]).query)
        self.assertEqual(query["api_key"], ["sam-secret"])
        self.assertEqual(query["title"], ["audio"])
        self.assertIn("postedFrom", query)
        self.assertEqual(results[0]["organization"], "Department of Defense")

    @patch("handler.urlopen")
    def test_sam_description_is_fetched_with_api_key(self, urlopen_mock):
        response = Mock()
        response.read.return_value = b"<html><body><p>Resilient voice communications over lossy networks.</p></body></html>"
        urlopen_mock.return_value.__enter__.return_value = response
        opportunity = {
            "id": "notice-2",
            "description_url": "https://api.sam.gov/opportunities/v1/noticedesc?noticeid=notice-2",
        }
        handler.fetch_sam_descriptions([opportunity], "sam-secret")
        request = urlopen_mock.call_args.args[0]
        self.assertIn("api_key=sam-secret", request.full_url)
        self.assertIn("Resilient voice communications", opportunity["description"])

    @patch("handler.http_json_request")
    def test_public_web_search_uses_authenticated_search_api(self, request):
        request.return_value = {"web": {"results": [{
            "title": "Electrical engineering RFP",
            "url": "https://example.test/rfp",
            "description": "Seeking an electrical design consultant.",
        }]}}
        results = handler.search_public_web("brave-secret", 14)
        self.assertEqual(request.call_count, 24)
        self.assertEqual(request.call_args.kwargs["headers"]["X-Subscription-Token"], "brave-secret")
        self.assertIn("after:", parse_qs(urlsplit(request.call_args.args[0]).query)["q"][0])
        self.assertEqual(results[0]["title"], "Electrical engineering RFP")
        self.assertEqual(results[0]["source"], "example.test")

    @patch("handler.http_json_request")
    def test_openai_scoring_request_is_parsed(self, request):
        request.return_value = {"choices": [{"message": {"content": json.dumps(scoring_payload(
            procurement_mode="integration_services",
            procurement_category="professional_services",
            company_overrides={
                "vivesound": {
                    "capability_relevance": 97,
                    "pursuit_fit": 91,
                    "existing_capability": True,
                    "why_it_fits": ["Audio SDK integration"],
                    "recommended_angle": "Integrate ViveEngine",
                },
            },
        ))}}]}
        result = handler.score_opportunity({"title": "Voice system"}, "openai-secret", "gpt-4o-mini")
        self.assertEqual(result["companies"]["vivesound"]["pursuit_fit"], 91)
        self.assertEqual(request.call_args.kwargs["headers"]["Authorization"], "Bearer openai-secret")
        payload = json.loads(request.call_args.kwargs["data"])
        self.assertEqual(payload["response_format"]["type"], "json_schema")
        company_schema = payload["response_format"]["json_schema"]["schema"]["properties"]["companies"]
        self.assertEqual(set(company_schema["required"]), set(handler.COMPANY_PROFILES))


if __name__ == "__main__":
    unittest.main()
