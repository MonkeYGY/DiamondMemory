import unittest
from unittest.mock import patch

from app.services.memory_service import MemoryService
import app.services.memory_service as memory_service_module


class DeepOrganizeLowPowerTests(unittest.TestCase):
    def test_deep_organize_low_power_runs_stages_with_limits(self):
        service = MemoryService.__new__(MemoryService)
        calls = []

        with patch.object(memory_service_module.settings, "deep_organize_low_power_enabled", True), \
             patch.object(memory_service_module.settings, "deep_organize_stage_pause_ms", 250), \
             patch.object(memory_service_module.settings, "deep_organize_cleanup_memory_limit", 3), \
             patch.object(memory_service_module.settings, "deep_organize_dedup_limit", 4), \
             patch.object(memory_service_module.settings, "deep_organize_reclassify_limit", 5), \
             patch.object(memory_service_module.settings, "deep_organize_cleanup_directory_limit", 2), \
             patch.object(memory_service_module.settings, "deep_organize_l1_batches_per_run", 1), \
             patch.object(memory_service_module.settings, "deep_organize_l2_batches_per_run", 2), \
             patch.object(memory_service_module.settings, "deep_organize_l4_batches_per_run", 3), \
             patch.object(service, "remove_low_quality_memories", side_effect=lambda limit=None: calls.append(("remove_low_quality_memories", limit)) or 1), \
             patch.object(service, "deduplicate_existing_l4", side_effect=lambda limit=None: calls.append(("deduplicate_existing_l4", limit)) or {"merged": 2}), \
             patch.object(service, "deduplicate_existing_l6", side_effect=lambda limit=None: calls.append(("deduplicate_existing_l6", limit)) or {"merged": 3}), \
             patch.object(service, "reclassify_default_l4", side_effect=lambda limit=None: calls.append(("reclassify_default_l4", limit)) or {"reclassified": 4}), \
             patch.object(service, "_batch_process_l1_to_l2_smart", side_effect=lambda max_batches=None: calls.append(("_batch_process_l1_to_l2_smart", max_batches)) or {"processed": 5}), \
             patch.object(service, "_batch_process_l2_to_l4_smart", side_effect=lambda max_batches=None: calls.append(("_batch_process_l2_to_l4_smart", max_batches)) or {"processed": 6}), \
             patch.object(service, "_batch_process_l4_to_l6_smart", side_effect=lambda max_batches=None: calls.append(("_batch_process_l4_to_l6_smart", max_batches)) or {"processed": 7}), \
             patch.object(service, "cleanup_empty_categories", side_effect=lambda memory_limit=None, directory_limit=None: calls.append(("cleanup_empty_categories", memory_limit, directory_limit)) or {"memories_deleted": 8, "directories_deleted": 1}), \
             patch.object(memory_service_module.time, "sleep", side_effect=lambda seconds: calls.append(("sleep", seconds))):
            result = service.organize_entire_knowledge_base()

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["details"]["l1_to_l2"], 5)
        self.assertEqual(result["details"]["l2_to_l4"], 6)
        self.assertEqual(result["details"]["l4_to_l6"], 7)
        self.assertEqual(result["details"]["cleanup_removed"], 1)
        self.assertEqual(result["details"]["l4_reclassified"], 4)
        self.assertEqual(result["details"]["cleanup_details"]["memories_deleted"], 8)
        self.assertEqual(
            calls,
            [
                ("remove_low_quality_memories", 3),
                ("sleep", 0.25),
                ("deduplicate_existing_l4", 4),
                ("sleep", 0.25),
                ("deduplicate_existing_l6", 4),
                ("sleep", 0.25),
                ("reclassify_default_l4", 5),
                ("sleep", 0.25),
                ("_batch_process_l1_to_l2_smart", 1),
                ("sleep", 0.25),
                ("_batch_process_l2_to_l4_smart", 2),
                ("sleep", 0.25),
                ("_batch_process_l4_to_l6_smart", 3),
                ("sleep", 0.25),
                ("cleanup_empty_categories", 3, 2),
            ],
        )


if __name__ == "__main__":
    unittest.main()
