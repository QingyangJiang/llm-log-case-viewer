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

    def test_five_chances_guarantee_success_and_later_stages_keep_path(self) -> None:
        _, _, evolution, _ = api.get_or_create_pet(self.db, self.user.id)
        evolution.available_chances = 10
        self.db.commit()

        with patch.object(api.secrets, "choice", side_effect=["wonky", "参差尖牙", "lucky_nose"]), patch.object(api.secrets, "randbelow", side_effect=[50, 2]):
            first = api.evolve_pet(api.PetEvolutionBody(spend=5), self.user, self.db)
        self.assertTrue(first["success"])
        self.assertEqual(first["profile"]["evolution_path"], "wonky")
        self.assertEqual(first["profile"]["evolution_stage"], 1)

        with patch.object(api.secrets, "choice", side_effect=["歪斜尾鳍", "treasure_paws"]), patch.object(api.secrets, "randbelow", side_effect=[50, 3]):
            second = api.evolve_pet(api.PetEvolutionBody(spend=5), self.user, self.db)
        self.assertTrue(second["success"])
        self.assertEqual(second["profile"]["evolution_path"], "wonky")
        self.assertEqual(second["profile"]["evolution_stage"], 2)
        self.assertEqual(second["profile"]["evolution_traits"], ["参差尖牙", "歪斜尾鳍"])

    def test_evolution_has_no_three_stage_cap_and_builds_on_same_path(self) -> None:
        _, _, evolution, _ = api.get_or_create_pet(self.db, self.user.id)
        evolution.available_chances = 5
        evolution.stage = 12
        evolution.path = "forest"
        evolution.traits = ["旧特征"]
        self.db.commit()

        with patch.object(api.secrets, "choice", side_effect=["森神化身", "collector"]), patch.object(api.secrets, "randbelow", side_effect=[50, 5]):
            result = api.evolve_pet(api.PetEvolutionBody(spend=5), self.user, self.db)

        self.assertTrue(result["success"])
        self.assertEqual(result["profile"]["evolution_path"], "forest")
        self.assertEqual(result["profile"]["evolution_stage"], 13)
        self.assertIn("星环1", result["trait"])

    def test_equipment_catalog_contains_three_hundred_items(self) -> None:
        self.assertEqual(len(api.PET_EQUIPMENT_CATALOG), 300)
        self.assertEqual(len({item["id"] for item in api.PET_EQUIPMENT_CATALOG.values()}), 300)

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
