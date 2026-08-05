import unittest
from unittest.mock import Mock, patch

from services.supabase_storage import (
    delete_object,
    download_bytes,
    enforce_user_storage_quota,
    parse_storage_reference,
    upload_bytes,
    user_storage_usage,
)
from services.resource_limits import ResourceLimitError


class SupabaseStorageTestCase(unittest.TestCase):
    def setUp(self):
        self.identity = patch(
            "services.supabase_storage.get_current_app_user_id",
            return_value="11111111-1111-1111-1111-111111111111",
        )
        self.url = patch(
            "services.supabase_storage.supabase_url",
            return_value="https://project.supabase.co",
        )
        self.key = patch(
            "services.supabase_storage.supabase_publishable_key",
            return_value="sb_publishable_test",
        )
        self.token = patch(
            "services.supabase_storage.current_id_token",
            return_value="header.payload.signature",
        )

        for mocked in (self.identity, self.url, self.key, self.token):
            mocked.start()

    def tearDown(self):
        patch.stopall()

    @patch("services.supabase_storage.requests.post")
    def test_upload_uses_private_user_prefix_and_auth0_id_token(self, post):
        post.return_value = Mock(ok=True, status_code=200)
        reference = upload_bytes(
            "library",
            "paper.pdf",
            b"pdf",
            content_type="application/pdf",
        )

        self.assertEqual(
            reference,
            "supabase://library/users/11111111-1111-1111-1111-111111111111/paper.pdf",
        )
        request = post.call_args
        self.assertEqual(
            request.args[0],
            "https://project.supabase.co/storage/v1/object/library/"
            "users/11111111-1111-1111-1111-111111111111/paper.pdf",
        )
        self.assertEqual(
            request.kwargs["headers"]["Authorization"],
            "Bearer header.payload.signature",
        )
        self.assertEqual(request.kwargs["headers"]["x-upsert"], "false")

    @patch("services.supabase_storage.requests.get")
    def test_download_rejects_cross_user_reference_before_http(self, get):
        foreign = (
            "supabase://library/users/"
            "22222222-2222-2222-2222-222222222222/paper.pdf"
        )

        with self.assertRaises(ValueError):
            download_bytes(foreign, bucket="library")

        get.assert_not_called()

    @patch("services.supabase_storage.requests.delete")
    def test_delete_uses_storage_remove_endpoint(self, delete):
        delete.return_value = Mock(ok=True, status_code=200)
        reference = (
            "supabase://audio/users/"
            "11111111-1111-1111-1111-111111111111/recording.wav"
        )
        delete_object(reference, bucket="audio")

        request = delete.call_args
        self.assertEqual(
            request.args[0],
            "https://project.supabase.co/storage/v1/object/audio",
        )
        self.assertEqual(
            request.kwargs["json"],
            {
                "prefixes": [
                    "users/11111111-1111-1111-1111-111111111111/recording.wav"
                ]
            },
        )

    def test_reference_parser_rejects_unknown_bucket(self):
        with self.assertRaises(ValueError):
            parse_storage_reference(
                "supabase://public/users/"
                "11111111-1111-1111-1111-111111111111/file.txt"
            )

    @patch("services.supabase_storage._walk_user_objects")
    def test_remote_quota_uses_storage_metadata(self, walk):
        walk.return_value = [
            ("users/id/a.pdf", {"metadata": {"size": 400}}),
            ("users/id/b.pdf", {"metadata": {"size": "500"}}),
        ]
        self.assertEqual(user_storage_usage("library"), (900, 2))

        with self.assertRaises(ResourceLimitError):
            enforce_user_storage_quota(
                "library",
                101,
                quota_bytes=1000,
                label="library",
                max_files=10,
            )


if __name__ == "__main__":
    unittest.main()
