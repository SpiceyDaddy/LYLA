import unittest

from src.task_tracker import ChatTaskTracker


class ChatTaskTrackerTests(unittest.TestCase):
    def test_task_moves_from_in_progress_to_completed_once(self):
        tracker = ChatTaskTracker()
        task = tracker.start("hello", "lyla", "automatic")

        self.assertEqual(task.status, "in_progress")
        self.assertIsNone(task.completed_at)

        completed = tracker.complete(task.task_id)

        self.assertEqual(completed.status, "completed")
        self.assertIsNotNone(completed.completed_at)
        self.assertIsNone(completed.error)
        with self.assertRaisesRegex(RuntimeError, "already completed"):
            tracker.complete(task.task_id)

    def test_failed_task_keeps_failure_detail(self):
        tracker = ChatTaskTracker()
        task = tracker.start("debug this", "jarvis", "automatic")

        failed = tracker.fail(task.task_id, "Model timed out.")

        self.assertEqual(failed.status, "failed")
        self.assertEqual(failed.error, "Model timed out.")
        self.assertIsNotNone(failed.completed_at)
        self.assertEqual(tracker.recent()[0]["task_id"], task.task_id)

    def test_history_evicts_old_finished_tasks_but_not_active_tasks(self):
        tracker = ChatTaskTracker(max_records=1)
        first = tracker.start("first", "lyla", "automatic")

        with self.assertRaisesRegex(RuntimeError, "limit of active chat tasks"):
            tracker.start("second", "lyla", "automatic")

        tracker.complete(first.task_id)
        second = tracker.start("second", "jarvis", "automatic")

        self.assertEqual(
            [task["task_id"] for task in tracker.recent()],
            [second.task_id],
        )

    def test_recent_limit_must_be_within_supported_bounds(self):
        tracker = ChatTaskTracker()
        with self.assertRaisesRegex(ValueError, "history limit"):
            tracker.recent(0)
        with self.assertRaisesRegex(ValueError, "at least one record"):
            ChatTaskTracker(max_records=0)


if __name__ == "__main__":
    unittest.main()
