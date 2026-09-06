import os
import unittest
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite://")

import backend.app.main as api


class PetEvolutionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = api.create_engine("sqlite://", connect_args={"check_same_thread": False})
        self.session_factory = api.sessionmaker(self.engine, expire_on_commit=False)
        api.Base.metadata.create_all(self.engine)
        self.db = self.session_factory()
        self.user = api.User(username="pet-owner", display_name="Pet Owner", password_hash="unused", role="annotator")
        self.db.add(self.user)
        self.db.flush()
        self.db.add(api.PetProfile(user_id=self.user.id))
        self.db.add(api.PetProgressV2(user_id=self.user.id, xp_units=400))
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_existing_levels_credit_one_chance_per_upgrade_once(self) -> None:
        _, _, evolution, _ = api.get_or_create_pet(self.db, self.user.id)
        self.assertEqual(api.pet_level(80), 3)
        self.assertEqual(evolution.available_chances, 2)
        self.assertEqual(evolution.credited_level, 3)
        self.db.commit()

        _, _, same_evolution, _ = api.get_or_create_pet(self.db, self.user.id)
        self.assertEqual(same_evolution.available_chances, 2)

    def test_level_curve_caps_at_50_and_stays_flat_after_level_five(self) -> None:
        self.assertEqual(api.pet_level_start_xp(4), 180)
        self.assertEqual(api.pet_level_start_xp(5), 320)
        self.assertEqual(api.pet_level_start_xp(6), 460)
        self.assertEqual(api.pet_level_start_xp(50), 6620)
        self.assertEqual(api.pet_level(459.9), 5)
        self.assertEqual(api.pet_level(460), 6)
        self.assertEqual(api.pet_level(100000), 50)

    def test_single_attempt_is_consumed_and_can_fail(self) -> None:
        api.get_or_create_pet(self.db, self.user.id)
        self.db.commit()
        with patch.object(api.secrets, "randbelow", return_value=77):
            result = api.evolve_pet(api.PetEvolutionBody(spend=1), self.user, self.db)

        self.assertFalse(result["success"])
        self.assertEqual(result["profile"]["evolution_chances"], 1)
        self.assertEqual(result["profile"]["evolution_stage"], 0)

    def test_five_chances_guarantee_success_and_reroute_from_stage_one(self) -> None:
        _, _, evolution, _ = api.get_or_create_pet(self.db, self.user.id)
        evolution.available_chances = 10
        self.db.commit()

        with patch.object(api.secrets, "choice", side_effect=["wonky", "参差尖牙", "lucky_nose"]), patch.object(api.secrets, "randbelow", side_effect=[50, 2]):
            first = api.evolve_pet(api.PetEvolutionBody(spend=5), self.user, self.db)
        self.assertTrue(first["success"])
        self.assertEqual(first["profile"]["evolution_path"], "wonky")
        self.assertEqual(first["profile"]["evolution_stage"], 1)

        with patch.object(api.secrets, "choice", side_effect=["forest", "新芽鹿角", "treasure_paws"]), patch.object(api.secrets, "randbelow", side_effect=[3]):
            second = api.evolve_pet(api.PetEvolutionBody(spend=5), self.user, self.db)
        self.assertTrue(second["success"])
        self.assertTrue(second["route_reset"])
        self.assertEqual(second["previous_path"], "wonky")
        self.assertEqual(second["profile"]["evolution_path"], "forest")
        self.assertEqual(second["profile"]["evolution_stage"], 1)
        self.assertEqual(second["profile"]["evolution_traits"], ["新芽鹿角"])

    def test_evolution_has_no_three_stage_cap_and_builds_on_same_path(self) -> None:
        _, _, evolution, _ = api.get_or_create_pet(self.db, self.user.id)
        evolution.available_chances = 1
        evolution.stage = 12
        evolution.path = "forest"
        evolution.traits = ["旧特征"]
        self.db.commit()

        with patch.object(api.secrets, "choice", side_effect=["森神化身", "collector"]), patch.object(api.secrets, "randbelow", side_effect=[0, 50, 5]):
            result = api.evolve_pet(api.PetEvolutionBody(spend=1), self.user, self.db)

        self.assertTrue(result["success"])
        self.assertEqual(result["profile"]["evolution_path"], "forest")
        self.assertEqual(result["profile"]["evolution_stage"], 13)
        self.assertIn("星环1", result["trait"])

    def test_equipment_catalog_contains_three_hundred_items(self) -> None:
        self.assertEqual(len(api.PET_EQUIPMENT_CATALOG), 300)
        self.assertEqual(len({item["id"] for item in api.PET_EQUIPMENT_CATALOG.values()}), 300)

    def test_legacy_equipment_levels_are_preserved_and_activate_set_bonuses(self) -> None:
        _, _, _, collection = api.get_or_create_pet(self.db, self.user.id)
        item_ids = ["gear-01-1-1", "gear-01-2-2", "gear-01-3-3", "gear-01-4-4", "gear-01-5-5"]
        collection.inventory = dict(zip(item_ids, [1, 3, 5, 5, 5]))
        collection.equipped = dict(zip(api.PET_EQUIPMENT_SLOTS, item_ids))

        payload = api.pet_collection_payload(collection)
        levels = {item["id"]: item["level"] for item in payload["inventory"]}
        self.assertEqual(levels["gear-01-1-1"], 1)
        self.assertEqual(levels["gear-01-2-2"], 3)
        self.assertEqual(levels["gear-01-3-3"], 5)
        self.assertEqual(payload["equipment_stats"]["total_power"], 29)
        self.assertEqual(payload["equipment_stats"]["all_drop_bonus"], 2)
        self.assertEqual(payload["equipment_stats"]["rarity_boost"], 1)
        self.assertEqual(payload["equipment_stats"]["evolution_bonus"], 6)
        self.assertEqual(payload["equipment_sets"][0]["pieces"], 5)
        self.assertEqual(len(payload["equipment_sets"][0]["bonuses"]), 3)

    def test_new_inventory_entries_do_not_auto_level_from_duplicate_count(self) -> None:
        item = api.PET_EQUIPMENT_CATALOG["gear-01-1-1"]
        entry = {"count": 7, "level": 2, "affixes": [], "synthesis_failures": 0}
        payload = api.pet_equipment_effect(item, entry)
        self.assertEqual(payload["count"], 7)
        self.assertEqual(payload["level"], 2)

    def test_synthesis_consumes_two_materials_and_has_failure_pity(self) -> None:
        item = api.PET_EQUIPMENT_CATALOG["gear-01-1-1"]
        raw_entry = {"count": 5, "level": 1, "affixes": [], "synthesis_failures": 0}
        generated = {"id": "affix-test", "key": "all_drop_bonus", "label": "所有装备掉率", "value": 2, "critical": True}
        with patch.object(api.secrets, "randbelow", side_effect=[0, 99]), patch.object(api, "pet_random_affix", return_value=generated):
            entry, success, success_rate, affixes = api.synthesize_pet_equipment_entry(item, raw_entry)
        self.assertTrue(success)
        self.assertEqual(success_rate, 90)
        self.assertEqual(entry["count"], 3)
        self.assertEqual(entry["level"], 2)
        self.assertEqual(affixes, [generated])

        with patch.object(api.secrets, "randbelow", return_value=99):
            failed, success, success_rate, affixes = api.synthesize_pet_equipment_entry(item, {**entry, "count": 3})
        self.assertFalse(success)
        self.assertEqual(success_rate, 80)
        self.assertEqual(failed["count"], 1)
        self.assertEqual(failed["level"], 2)
        self.assertEqual(failed["synthesis_failures"], 1)
        self.assertEqual(failed["affixes"], [generated])
        self.assertEqual(affixes, [])
        self.assertEqual(api.pet_synthesis_success_rate(failed), 85)

    def test_reforge_keeps_level_and_can_add_many_random_affixes(self) -> None:
        item = api.PET_EQUIPMENT_CATALOG["gear-01-1-1"]
        raw_entry = {"count": 4, "level": 6, "affixes": [{"id": "old", "key": "pet_drop_bonus", "value": 1}], "synthesis_failures": 2}
        with patch.object(api.secrets, "randbelow", return_value=0), patch.object(api, "pet_random_affix", side_effect=lambda _item, _level, index: {"id": f"new-{index}", "key": "rarity_boost", "label": "稀有装备权重", "value": index + 1, "critical": False}):
            entry, affixes = api.reforge_pet_equipment_entry(item, raw_entry)
        self.assertEqual(entry["count"], 3)
        self.assertEqual(entry["level"], 6)
        self.assertEqual(entry["synthesis_failures"], 2)
        self.assertEqual(len(affixes), 2)

    def test_annotation_drop_base_chance_is_eighteen_percent(self) -> None:
        _, _, _, collection = api.get_or_create_pet(self.db, self.user.id)
        self.assertEqual(api.PET_DROP_BASE_CHANCES["pet"], 500)
        self.assertEqual(api.PET_DROP_BASE_CHANCES["annotation"], 1800)
        self.assertEqual(api.PET_DROP_BASE_CHANCES["badcase"], 2000)
        with patch.object(api.secrets, "randbelow", return_value=1800):
            self.assertIsNone(api.maybe_drop_pet_equipment(collection, "annotation"))

    def test_drop_creates_three_hidden_choices_and_claims_only_one(self) -> None:
        _, _, _, collection = api.get_or_create_pet(self.db, self.user.id)
        hidden_affixes = [
            {"id": f"hidden-{index}", "key": "all_drop_bonus", "label": "所有装备掉率", "value": index + 1, "critical": index == 2}
            for index in range(3)
        ]
        with patch.object(api, "pet_choose_rarity", return_value="common"), patch.object(api.secrets, "randbelow", return_value=0), patch.object(api.secrets, "choice", side_effect=lambda choices: choices[0]), patch.object(api.secrets, "token_hex", return_value="drop-token"), patch.object(api, "pet_random_affix", side_effect=hidden_affixes):
            self.assertIsNone(api.maybe_drop_pet_equipment(collection, "annotation"))

        pending = api.pet_pending_drops(collection)
        public = api.pet_pending_drop_payload(collection)
        self.assertEqual(len(pending), 1)
        self.assertEqual(len(public[0]["choices"]), 3)
        self.assertEqual(len({choice["id"] for choice in public[0]["choices"]}), 3)
        self.assertNotIn("hidden_affix", public[0]["choices"][0])
        self.assertEqual(collection.total_drops, 0)

        selected_id = public[0]["choices"][0]["id"]
        drop, affix, added = api.claim_pet_drop_choice(collection, "drop-token", selected_id)
        self.assertTrue(added)
        self.assertEqual(affix["id"], "hidden-0")
        self.assertEqual(drop["count"], 1)
        self.assertEqual(drop["affixes"][0]["id"], "hidden-0")
        self.assertEqual(collection.total_drops, 1)
        self.assertEqual(api.pet_pending_drops(collection), [])

    def test_admin_can_gift_tickets_after_password_recheck(self) -> None:
        admin = api.User(username="admin-pet", display_name="Admin", password_hash=api.hash_password("ticket-secret"), role="admin")
        self.db.add(admin)
        self.db.commit()
        result = api.gift_pet_tickets(api.PetTicketGiftBody(recipient_user_id=self.user.id, amount=7, password="ticket-secret", note="奖励"), admin, self.db)
        self.assertEqual(result["amount"], 7)
        self.assertEqual(result["profile"]["evolution_chances"], 9)
        self.assertEqual(self.db.scalar(api.select(api.PetTicketGift.amount)), 7)


if __name__ == "__main__":
    unittest.main()
