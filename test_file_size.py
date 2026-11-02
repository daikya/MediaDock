import unittest

from gui import (
    format_file_size,
    get_format_size,
    get_selected_formats_size,
)


class FileSizeTests(unittest.TestCase):

    def test_exact_size(self):
        self.assertEqual(
            get_format_size({"filesize": 524288000}),
            524288000,
        )

    def test_approximate_size(self):
        self.assertEqual(
            get_format_size({"filesize_approx": 157286400}),
            157286400,
        )

    def test_combined_video_audio(self):
        info = {
            "requested_formats": [
                {"format_id": "136", "filesize": 7694487},
                {"format_id": "140", "filesize": 974912},
            ]
        }
        self.assertEqual(get_selected_formats_size(info), 8669399)

    def test_single_format(self):
        self.assertEqual(
            get_selected_formats_size({"filesize": 52428800}),
            52428800,
        )

    def test_unknown_size(self):
        self.assertIsNone(
            get_selected_formats_size({
                "requested_formats": [
                    {"filesize": 1000},
                    {},
                ]
            })
        )

    def test_display_format(self):
        self.assertEqual(format_file_size(8669399), "約 8.3 MB")
        self.assertEqual(format_file_size(None), "不明")


if __name__ == "__main__":
    unittest.main()
