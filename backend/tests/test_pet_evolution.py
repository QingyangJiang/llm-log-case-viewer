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
        collection.inventory = {item_id: {"count": 1, "level": 2, "affixes": [], "synthesis_failures": 0}}
        collection.equipped = {"head": item_id}
        profile.color = "aqua"
        profile.accessory = "leaf"
        self.db.commit()

        saved = api.manage_pet_wardrobe(api.PetWardrobeBody(action="save", name="寻宝套"), self.user, self.db)
        presets = saved["profile"]["wardrobe_presets"]
        self.assertEqual(len(presets), 1)
        self.assertEqual(presets[0]["name"], "寻宝套")
        self.assertEqual(presets[0]["equipped"], {"head": item_id})

        profile.color = "lime"
        profile.accessory = "none"
        collection.equipped = {}
        self.db.commit()
        applied = api.manage_pet_wardrobe(api.PetWardrobeBody(action="apply", preset_id=presets[0]["id"]), self.user, self.db)
        self.assertEqual(applied["profile"]["color"], "aqua")
        self.assertEqual(applied["profile"]["accessory"], "leaf")
        self.assertEqual(applied["profile"]["equipped"], {"head": item_id})

        deleted = api.manage_pet_wardrobe(api.PetWardrobeBody(action="delete", preset_id=presets[0]["id"]), self.user, self.db)
        self.assertEqual(deleted["profile"]["wardrobe_presets"], [])

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

    def test_dismantle_two_items_then_random_forge_can_level_up(self) -> None:
        _, _, _, collection = api.get_or_create_pet(self.db, self.user.id)
        source_id = "gear-01-1-1"
        collection.inventory = {source_id: {"count": 2, "level": 4, "affixes": [], "synthesis_failures": 0}}

        _, parts = api.dismantle_pet_equipment(collection, source_id)
        self.assertEqual(parts, 1)
        _, parts = api.dismantle_pet_equipment(collection, source_id)
        self.assertEqual(parts, 2)
        self.assertNotIn(source_id, collection.inventory)

        generated = {"id": "forge-affix", "key": "all_drop_bonus", "label": "所有装备掉率", "value": 2, "critical": True}
        with patch.object(api, "pet_choose_rarity", return_value="common"), patch.object(api.secrets, "choice", side_effect=lambda choices: choices[0]), patch.object(api.secrets, "randbelow", return_value=0), patch.object(api, "pet_random_affix", return_value=generated):
            item, level_up, affix, affix_added = api.forge_random_pet_equipment(collection)

        self.assertTrue(level_up)
        self.assertTrue(affix_added)
        self.assertEqual(affix, generated)
        self.assertEqual(item["level"], 2)
        self.assertEqual(item["count"], 1)
        self.assertEqual(item["affixes"], [generated])
        self.assertEqual(api.pet_equipment_parts(collection), 0)

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

    def test_homestead_lists_other_pets_with_appearance_route_and_power(self) -> None:
        _, _, my_evolution, _ = api.get_or_create_pet(self.db, self.user.id)
        my_evolution.path = "forest"
        my_evolution.stage = 2
        neighbor, profile, progress, evolution, collection = self.add_opponent()
        profile.name = "小雷"
        profile.color = "sky"
        profile.accessory = "glasses"
        progress.xp_units = api.pet_level_start_xp(8) * 5
        evolution.path = "storm"
        evolution.stage = 4
        evolution.traits = ["闪电耳羽", "疾风羽翼"]
        item_id = "gear-03-1-3"
        collection.inventory = {item_id: {"count": 1, "level": 3, "affixes": [], "synthesis_failures": 0}}
        collection.equipped = {"head": item_id}
        self.db.commit()

        home = api.pet_homestead_payload(self.db, self.user)

        self.assertEqual(home["resident_count"], 2)
        self.assertTrue(home["battle_available"])
        self.assertEqual(len(home["residents"]), 1)
        resident = home["residents"][0]
        self.assertEqual(resident["user_id"], str(neighbor.id))
        self.assertEqual(resident["pet_name"], "小雷")
        self.assertEqual(resident["color"], "sky")
        self.assertEqual(resident["accessory"], "glasses")
        self.assertEqual(resident["evolution_path"], "storm")
        self.assertEqual(resident["evolution_stage"], 4)
        self.assertEqual(resident["equipped_items"][0]["id"], item_id)
        self.assertGreater(resident["battle_power"], 0)
        self.assertEqual(resident["battle_power"], sum(resident["power_breakdown"].values()))
        self.assertNotIn("inventory", resident)
        self.assertNotIn("password_hash", resident)

    def test_daily_battle_win_queues_guaranteed_drop_and_cannot_repeat(self) -> None:
        _, progress, evolution, collection = api.get_or_create_pet(self.db, self.user.id)
        progress.xp_units = api.pet_level_start_xp(20) * 5
        evolution.path = "guardian"
        evolution.stage = 8
        self.add_opponent()
        self.db.commit()

        with patch.object(api.secrets, "choice", side_effect=lambda choices: choices[0]), patch.object(api.secrets, "randbelow", return_value=0), patch.object(api.secrets, "token_hex", side_effect=["battle-drop", "battle-event"]):
            result = api.battle_pet_in_homestead(self.user, self.db)

        self.assertTrue(result["won"])
        self.assertEqual(result["outcome"], "win")
        self.assertGreater(result["my_power"], result["opponent_power"])
        self.assertEqual(result["reward_pending"]["reason"], "battle")
        self.assertEqual(len(result["reward_pending"]["choices"]), 3)
        self.assertEqual(result["profile"]["pending_drops"][0]["token"], "battle-drop")
        self.assertFalse(result["home"]["battle_available"])
        state = api.pet_battle_state(collection)
        self.assertEqual(state["last_battle_date"], api.pet_battle_day())
        self.assertEqual(state["history"][0]["outcome"], "win")

        with self.assertRaises(api.HTTPException) as raised:
            api.battle_pet_in_homestead(self.user, self.db)
        self.assertEqual(raised.exception.status_code, 409)

    def test_daily_battle_loss_consumes_chance_without_drop(self) -> None:
        api.get_or_create_pet(self.db, self.user.id)
        _, _, progress, evolution, _ = self.add_opponent()
        progress.xp_units = api.pet_level_start_xp(30) * 5
        evolution.path = "starlight"
        evolution.stage = 12
        self.db.commit()

        with patch.object(api.secrets, "choice", side_effect=lambda choices: choices[0]), patch.object(api.secrets, "randbelow", return_value=99), patch.object(api.secrets, "token_hex", return_value="loss-event"):
            result = api.battle_pet_in_homestead(self.user, self.db)

        self.assertFalse(result["won"])
        self.assertEqual(result["outcome"], "loss")
        self.assertIsNone(result["reward_pending"])
        self.assertEqual(result["profile"]["pending_drops"], [])
        self.assertFalse(result["home"]["battle_available"])

    def test_daily_battle_loss_has_ten_percent_lucky_drop(self) -> None:
        api.get_or_create_pet(self.db, self.user.id)
        _, _, progress, evolution, _ = self.add_opponent()
        progress.xp_units = api.pet_level_start_xp(30) * 5
        evolution.path = "starlight"
        evolution.stage = 12
        self.db.commit()

        with patch.object(api.secrets, "choice", side_effect=lambda choices: choices[0]), patch.object(api.secrets, "randbelow", return_value=0), patch.object(api.secrets, "token_hex", side_effect=["lucky-drop", "loss-event"]):
            result = api.battle_pet_in_homestead(self.user, self.db)

        self.assertFalse(result["won"])
        self.assertEqual(result["outcome"], "loss")
        self.assertTrue(result["lucky_reward"])
        self.assertEqual(result["reward_pending"]["reason"], "battle")
        self.assertEqual(result["profile"]["pending_drops"][0]["token"], "lucky-drop")
        self.assertTrue(api.pet_battle_state(self.db.scalar(api.select(api.PetCollection).where(api.PetCollection.user_id == self.user.id)))["history"][0]["reward"])

    def test_battle_day_uses_china_calendar_day(self) -> None:
        before_midnight = api.datetime(2026, 9, 8, 15, 59, tzinfo=api.timezone.utc)
        after_midnight = api.datetime(2026, 9, 8, 16, 1, tzinfo=api.timezone.utc)
        self.assertEqual(api.pet_battle_day(before_midnight), "2026-09-08")
        self.assertEqual(api.pet_battle_day(after_midnight), "2026-09-09")
        self.assertEqual(api.pet_next_battle_at(before_midnight), "2026-09-08T16:00:00+00:00")

    def test_admin_can_bulk_gift_tickets_to_annotators_and_admins_without_password(self) -> None:
        admin = api.User(username="admin-pet", display_name="Admin", password_hash=api.hash_password("ticket-secret"), role="admin")
        other_admin = api.User(username="admin-other", display_name="Other Admin", password_hash="unused", role="admin")
        self.db.add_all([admin, other_admin])
        self.db.commit()
        result = api.gift_pet_tickets(api.PetTicketGiftBody(recipient_user_ids=[self.user.id, admin.id, other_admin.id], amount=7, note="奖励"), admin, self.db)
        self.assertEqual(result["amount"], 7)
        self.assertEqual(result["total_amount"], 21)
        self.assertEqual(len(result["recipients"]), 3)
        self.assertEqual(result["profile"]["evolution_chances"], 9)
        admin_evolution = self.db.scalar(api.select(api.PetEvolution).where(api.PetEvolution.user_id == admin.id))
        other_admin_evolution = self.db.scalar(api.select(api.PetEvolution).where(api.PetEvolution.user_id == other_admin.id))
        self.assertEqual(admin_evolution.available_chances, 7)
        self.assertEqual(other_admin_evolution.available_chances, 7)
        self.assertEqual(len(self.db.scalars(api.select(api.PetTicketGift)).all()), 3)

    def test_admin_can_grant_wheel_chances_and_recipient_spins_them(self) -> None:
        admin = api.User(username="wheel-admin", display_name="Wheel Admin", password_hash="unused", role="admin")
        self.db.add(admin)
        self.db.commit()

        granted = api.gift_pet_wheel_chances(
            api.PetWheelGrantBody(recipient_user_ids=[self.user.id, admin.id], amount=3, note="周赛奖励"),
            admin,
            self.db,
        )
        self.assertEqual(granted["total_amount"], 6)
        self.assertEqual(granted["profile"]["wheel_chances"], 3)
        self.assertEqual(len(self.db.scalars(api.select(api.PetWheelGrant)).all()), 2)
        _, _, evolution, collection = api.get_or_create_pet(self.db, self.user.id)
        chances_before = evolution.available_chances
        self.assertEqual(api.pet_wheel_state(collection)["chances"], 3)

        with patch.object(api.secrets, "randbelow", return_value=0), patch.object(api.secrets, "token_hex", return_value="wheel-event"):
            result = api.spin_pet_wheel(self.user, self.db)

        self.assertEqual(result["reward_index"], 0)
        self.assertEqual(result["reward"]["reward_id"], "ticket_1")
        self.assertEqual(result["profile"]["wheel_chances"], 2)
        self.assertEqual(result["profile"]["evolution_chances"], chances_before + 1)
        self.assertEqual(result["profile"]["wheel_history"][0]["id"], "wheel-event")
        self.assertEqual(sum(reward["weight"] for reward in api.PET_WHEEL_REWARDS), 10_000)

    def test_wheel_rejects_spin_without_available_chance(self) -> None:
        api.get_or_create_pet(self.db, self.user.id)
        self.db.commit()
        with self.assertRaises(api.HTTPException) as raised:
            api.spin_pet_wheel(self.user, self.db)
        self.assertEqual(raised.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
