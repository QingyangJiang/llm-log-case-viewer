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

    def add_opponent(self, username: str = "pet-neighbor", display_name: str = "Pet Neighbor"):
        opponent = api.User(username=username, display_name=display_name, password_hash="unused", role="annotator")
        self.db.add(opponent)
        self.db.flush()
        profile, progress, evolution, collection = api.get_or_create_pet(self.db, opponent.id)
        self.db.commit()
        return opponent, profile, progress, evolution, collection

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

    def test_expanded_pet_colors_unlock_by_level(self) -> None:
        self.assertEqual(len(api.PET_COLORS), 20)
        with self.assertRaises(api.HTTPException) as raised:
            api.update_pet(api.PetProfileUpdate(name="小镜", color="cosmos", accessory="none"), self.user, self.db)
        self.assertEqual(raised.exception.status_code, 422)
        progress = self.db.scalar(api.select(api.PetProgressV2).where(api.PetProgressV2.user_id == self.user.id))
        progress.xp_units = api.pet_level_start_xp(50) * 5
        self.db.commit()
        profile = api.update_pet(api.PetProfileUpdate(name="小镜", color="cosmos", accessory="none"), self.user, self.db)
        self.assertEqual(profile["color"], "cosmos")

    def test_fashion_catalog_has_sixty_pieces_and_enforces_level_unlocks(self) -> None:
        self.assertEqual(len(api.PET_FASHION_CATALOG), 60)
        with self.assertRaises(api.HTTPException) as raised:
            api.update_pet(api.PetProfileUpdate(
                name="小镜",
                color="peach",
                accessory="bow",
                fashion={"outfit": "fashion-cosmos-outfit"},
            ), self.user, self.db)
        self.assertEqual(raised.exception.status_code, 422)

        saved = api.update_pet(api.PetProfileUpdate(
            name="小镜",
            color="peach",
            accessory="bow",
            fashion={"headwear": "fashion-academy-headwear", "outfit": "fashion-academy-outfit"},
        ), self.user, self.db)
        self.assertEqual(saved["fashion"]["headwear"], "fashion-academy-headwear")
        self.assertEqual(saved["fashion_catalog_size"], 60)

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
        self.assertEqual(second["wheel_compensation"], 2)
        self.assertEqual(second["profile"]["wheel_chances"], 2)

    def test_ten_ticket_targeted_reroute_stacks_failures_and_compensates_old_stage(self) -> None:
        _, _, evolution, _ = api.get_or_create_pet(self.db, self.user.id)
        evolution.available_chances = 30
        evolution.stage = 4
        evolution.path = "forest"
        evolution.traits = ["旧特征"]
        self.db.commit()

        with patch.object(api.secrets, "randbelow", return_value=99):
            failed = api.evolve_pet(api.PetEvolutionBody(spend=10, target_path="storm"), self.user, self.db)
        self.assertFalse(failed["success"])
        self.assertTrue(failed["targeted"])
        self.assertEqual(failed["profile"]["evolution_path"], "forest")
        self.assertEqual(failed["profile"]["evolution_stage"], 4)
        self.assertEqual(failed["profile"]["targeted_evolution_target"], "storm")
        self.assertEqual(failed["profile"]["targeted_evolution_failures"], 1)
        self.assertEqual(failed["profile"]["targeted_evolution_success_rate"], 80)

        with patch.object(api.secrets, "randbelow", side_effect=[79, 3]), patch.object(api.secrets, "choice", side_effect=["闪电耳羽", "lucky_nose"]):
            succeeded = api.evolve_pet(api.PetEvolutionBody(spend=10, target_path="storm"), self.user, self.db)
        self.assertTrue(succeeded["success"])
        self.assertTrue(succeeded["route_reset"])
        self.assertEqual(succeeded["success_rate"], 80)
        self.assertEqual(succeeded["wheel_compensation"], 8)
        self.assertEqual(succeeded["profile"]["wheel_chances"], 8)
        self.assertEqual(succeeded["profile"]["evolution_path"], "storm")
        self.assertEqual(succeeded["profile"]["evolution_stage"], 1)
        self.assertEqual(succeeded["profile"]["targeted_evolution_failures"], 0)

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
        self.assertEqual(len(api.PET_EQUIPMENT_SET_EFFECTS), 12)
        signatures = {tuple((key, value) for _, key, value, _ in definition["tiers"]) for definition in api.PET_EQUIPMENT_SET_EFFECTS.values()}
        self.assertEqual(len(signatures), 12)

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
        self.assertEqual(payload["equipment_stats"]["all_drop_bonus"], 3)
        self.assertEqual(payload["equipment_stats"]["rarity_boost"], 1)
        self.assertEqual(payload["equipment_stats"]["evolution_bonus"], 7)
        self.assertEqual(payload["equipment_sets"][0]["pieces"], 5)
        self.assertEqual(len(payload["equipment_sets"][0]["bonuses"]), 3)
        self.assertEqual(payload["equipment_sets"][0]["name"], "星愿引力")
        self.assertTrue(all(tier["active"] for tier in payload["equipment_sets"][0]["tiers"]))

    def test_auto_equip_uses_owned_items_and_never_reduces_selected_goal(self) -> None:
        _, _, _, collection = api.get_or_create_pet(self.db, self.user.id)
        item_ids = ["gear-01-1-1", "gear-01-2-2", "gear-01-3-3", "gear-01-4-4", "gear-01-5-5"]
        collection.inventory = {
            item_id: {"count": 1, "level": index + 1, "affixes": [], "synthesis_failures": 0}
            for index, item_id in enumerate(item_ids)
        }
        collection.equipped = {"head": item_ids[0]}
        before = api.pet_loadout_score(collection, collection.equipped, "evolution")

        equipped, reported_before, after = api.pet_auto_equip(collection, "evolution")

        self.assertEqual(reported_before, before)
        self.assertGreaterEqual(after, before)
        self.assertEqual(set(equipped), set(api.PET_EQUIPMENT_SLOTS))
        self.assertTrue(all(item_id in collection.inventory for item_id in equipped.values()))
        self.assertEqual(api.pet_equipment_state(collection)[0]["evolution_bonus"], after[0])

    def test_wardrobe_saves_applies_and_deletes_a_complete_look(self) -> None:
        profile, _, _, collection = api.get_or_create_pet(self.db, self.user.id)
        item_id = "gear-01-1-1"
        collection.inventory = {
            item_id: {"count": 1, "level": 2, "affixes": [], "synthesis_failures": 0},
            api.PET_FASHION_KEY: {"headwear": "fashion-academy-headwear", "outfit": "fashion-academy-outfit"},
        }
        collection.equipped = {"head": item_id}
        profile.color = "aqua"
        profile.accessory = "leaf"
        self.db.commit()

        saved = api.manage_pet_wardrobe(api.PetWardrobeBody(action="save", name="寻宝套"), self.user, self.db)
        presets = saved["profile"]["wardrobe_presets"]
        self.assertEqual(len(presets), 1)
        self.assertEqual(presets[0]["name"], "寻宝套")
        self.assertEqual(presets[0]["equipped"], {"head": item_id})
        self.assertEqual(presets[0]["fashion"]["outfit"], "fashion-academy-outfit")

        profile.color = "lime"
        profile.accessory = "none"
        collection.equipped = {}
        collection.inventory[api.PET_FASHION_KEY] = {}
        self.db.commit()
        applied = api.manage_pet_wardrobe(api.PetWardrobeBody(action="apply", preset_id=presets[0]["id"]), self.user, self.db)
        self.assertEqual(applied["profile"]["color"], "aqua")
        self.assertEqual(applied["profile"]["accessory"], "leaf")
        self.assertEqual(applied["profile"]["fashion"]["headwear"], "fashion-academy-headwear")
        self.assertEqual(applied["profile"]["equipped"], {"head": item_id})

        deleted = api.manage_pet_wardrobe(api.PetWardrobeBody(action="delete", preset_id=presets[0]["id"]), self.user, self.db)
        self.assertEqual(deleted["profile"]["wardrobe_presets"], [])

    def test_legacy_wardrobe_without_fashion_preserves_current_clothes(self) -> None:
        _, _, _, collection = api.get_or_create_pet(self.db, self.user.id)
        collection.inventory = {
            api.PET_FASHION_KEY: {"outfit": "fashion-academy-outfit"},
            api.PET_WARDROBE_KEY: [{
                "id": "legacy-look",
                "name": "旧搭配",
                "color": "aqua",
                "accessory": "leaf",
                "equipped": {},
                "created_at": api.utcnow().isoformat(),
            }],
        }
        self.db.commit()

        applied = api.manage_pet_wardrobe(api.PetWardrobeBody(action="apply", preset_id="legacy-look"), self.user, self.db)

        self.assertFalse(applied["profile"]["wardrobe_presets"][0]["fashion_saved"])
        self.assertEqual(applied["profile"]["fashion"], {"outfit": "fashion-academy-outfit"})

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
        with patch.object(api.secrets, "randbelow", retur