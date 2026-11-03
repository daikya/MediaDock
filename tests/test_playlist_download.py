
"""プレイリストのダウンロード処理のテスト。"""

import queue
import threading
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import gui


def make_fake_process(
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
    download: bool = False,
) -> MagicMock:
    """外部プログラムを起動しないテスト用プロセスを作成する。"""
    process = MagicMock()
    process.pid = 12345
    process.returncode = returncode
    process.poll.return_value = returncode
    process.communicate.return_value = (stdout, stderr)
    process.wait.return_value = returncode

    if download:
        process.stdout = iter(
            ["MEDIADOCK_PROGRESS:100.0%\n"]
        )

    process.__enter__.return_value = process
    process.__exit__.return_value = False

    return process


def test_playlist_continues_after_filename_failure(tmp_path: Path) -> None:
    """2本目のファイル名取得に失敗しても3本目まで処理する。"""
    application = object.__new__(gui.MediaDockGUI)
    application.application_directory = tmp_path
    application.playlist_videos = [
        {"id": "video001", "title": "動画1"},
        {"id": "video002", "title": "動画2"},
        {"id": "video003", "title": "動画3"},
    ]
    application.download_results = queue.Queue()
    application.playlist_download_status = queue.Queue()
    application.download_progress = queue.Queue()
    application.cancel_requested = threading.Event()
    application.download_process_lock = threading.Lock()
    application.download_process = None
    application.download_process_termination_requested = False

    deno_path = tmp_path / "deno.exe"
    deno_path.touch()

    ffmpeg_directory = tmp_path / "ffmpeg"
    ffmpeg_directory.mkdir()
    (ffmpeg_directory / "ffmpeg.exe").touch()


    filename_calls = []
    download_calls = []

    def fake_popen(command, **kwargs):
        video_url = command[-1]
        video_id = video_url.split("=")[-1]

        if "--simulate" in command:
            filename_calls.append(video_id)

            if video_id == "video002":
                return make_fake_process(
                    returncode=1,
                    stderr="テスト用の取得エラー",
                )

            return make_fake_process(
                stdout=str(tmp_path / f"{video_id}.mp4") + "\n",
            )

        download_calls.append(video_id)
        return make_fake_process(download=True)

    with (
        patch.object(gui, "download_yt_dlp", return_value=tmp_path / "yt-dlp.exe"),
        patch.object(gui, "download_deno", return_value=deno_path),
        patch.object(gui, "download_ffmpeg", return_value=ffmpeg_directory),
        patch.object(gui.subprocess, "Popen", side_effect=fake_popen),
    ):
        application.run_playlist_download(
            "https://www.youtube.com/playlist?list=test",
            720,
            tmp_path,
        )

    success, message = application.download_results.get_nowait()

    assert success is False
    assert "プレイリストの処理が一部失敗しました。" in message
    assert "対象動画数: 3本" in message
    assert "ダウンロード成功: 2本" in message
    assert "既存ファイルをスキップ: 0本" in message
    assert "失敗: 1本" in message
    assert "2/3本目: 動画2" in message
    assert "テスト用の取得エラー" in message

    assert filename_calls == ["video001", "video002", "video003"]
    assert download_calls == ["video001", "video003"]
    assert application.download_process is None


def test_playlist_continues_after_download_failure(tmp_path: Path) -> None:
    """2本目のダウンロードが失敗しても3本目まで処理する。"""
    application = object.__new__(gui.MediaDockGUI)
    application.application_directory = tmp_path
    application.playlist_videos = [
        {"id": "video001", "title": "動画1"},
        {"id": "video002", "title": "動画2"},
        {"id": "video003", "title": "動画3"},
    ]
    application.download_results = queue.Queue()
    application.playlist_download_status = queue.Queue()
    application.download_progress = queue.Queue()
    application.cancel_requested = threading.Event()
    application.download_process_lock = threading.Lock()
    application.download_process = None

    deno_path = tmp_path / "deno.exe"
    deno_path.touch()

    ffmpeg_directory = tmp_path / "ffmpeg"
    ffmpeg_directory.mkdir()
    (ffmpeg_directory / "ffmpeg.exe").touch()


    filename_calls = []
    download_calls = []

    def fake_popen(command, **kwargs):
        video_url = command[-1]
        video_id = video_url.split("=")[-1]

        if "--simulate" in command:
            filename_calls.append(video_id)

            return make_fake_process(
                stdout=str(tmp_path / f"{video_id}.mp4") + "\n",
            )

        download_calls.append(video_id)

        return make_fake_process(
            returncode=1 if video_id == "video002" else 0,
            download=True,
        )

    with (
        patch.object(gui, "download_yt_dlp", return_value=tmp_path / "yt-dlp.exe"),
        patch.object(gui, "download_deno", return_value=deno_path),
        patch.object(gui, "download_ffmpeg", return_value=ffmpeg_directory),
        patch.object(gui.subprocess, "Popen", side_effect=fake_popen),
    ):
        application.run_playlist_download(
            "https://www.youtube.com/playlist?list=test",
            720,
            tmp_path,
        )

    success, message = application.download_results.get_nowait()

    assert success is False
    assert "プレイリストの処理が一部失敗しました。" in message
    assert "対象動画数: 3本" in message
    assert "ダウンロード成功: 2本" in message
    assert "既存ファイルをスキップ: 0本" in message
    assert "失敗: 1本" in message
    assert "2/3本目: 動画2" in message
    assert "終了コード: 1" in message

    assert filename_calls == ["video001", "video002", "video003"]
    assert download_calls == ["video001", "video002", "video003"]
    assert application.download_process is None


def test_playlist_reports_all_videos_failed(tmp_path: Path) -> None:
    """すべての動画が失敗した場合は全件失敗として報告する。"""
    application = object.__new__(gui.MediaDockGUI)
    application.application_directory = tmp_path
    application.playlist_videos = [
        {"id": "video001", "title": "動画1"},
        {"id": "video002", "title": "動画2"},
        {"id": "video003", "title": "動画3"},
    ]
    application.download_results = queue.Queue()
    application.playlist_download_status = queue.Queue()
    application.download_progress = queue.Queue()
    application.cancel_requested = threading.Event()
    application.download_process_lock = threading.Lock()
    application.download_process = None

    deno_path = tmp_path / "deno.exe"
    deno_path.touch()

    ffmpeg_directory = tmp_path / "ffmpeg"
    ffmpeg_directory.mkdir()
    (ffmpeg_directory / "ffmpeg.exe").touch()

    filename_calls = []
    download_calls = []

    def fake_popen(command, **kwargs):
        video_id = command[-1].split("=")[-1]

        if "--simulate" in command:
            filename_calls.append(video_id)

            return make_fake_process(
                returncode=1,
                stderr="テスト用の取得エラー",
            )

        download_calls.append(video_id)
        return make_fake_process(download=True)

    with (
        patch.object(gui, "download_yt_dlp", return_value=tmp_path / "yt-dlp.exe"),
        patch.object(gui, "download_deno", return_value=deno_path),
        patch.object(gui, "download_ffmpeg", return_value=ffmpeg_directory),
        patch.object(gui.subprocess, "Popen", side_effect=fake_popen),
    ):
        application.run_playlist_download(
            "https://www.youtube.com/playlist?list=test",
            720,
            tmp_path,
        )

    success, message = application.download_results.get_nowait()

    assert success is False
    assert "プレイリストのダウンロードがすべて失敗しました。" in message
    assert "対象動画数: 3本" in message
    assert "ダウンロード成功: 0本" in message
    assert "既存ファイルをスキップ: 0本" in message
    assert "失敗: 3本" in message

    for index in range(1, 4):
        assert f"{index}/3本目: 動画{index}" in message

    assert filename_calls == ["video001", "video002", "video003"]
    assert download_calls == []
    assert application.download_process is None


def test_playlist_stops_after_cancellation(tmp_path: Path) -> None:
    """キャンセルされた場合は後続動画を処理しない。"""
    application = object.__new__(gui.MediaDockGUI)
    application.application_directory = tmp_path
    application.playlist_videos = [
        {"id": "video001", "title": "動画1"},
        {"id": "video002", "title": "動画2"},
        {"id": "video003", "title": "動画3"},
    ]
    application.download_results = queue.Queue()
    application.playlist_download_status = queue.Queue()
    application.download_progress = queue.Queue()
    application.cancel_requested = threading.Event()
    application.download_process_lock = threading.Lock()
    application.download_process = None

    deno_path = tmp_path / "deno.exe"
    deno_path.touch()

    ffmpeg_directory = tmp_path / "ffmpeg"
    ffmpeg_directory.mkdir()
    (ffmpeg_directory / "ffmpeg.exe").touch()

    filename_calls = []
    download_calls = []

    def fake_popen(command, **kwargs):
        video_id = command[-1].split("=")[-1]

        if "--simulate" in command:
            filename_calls.append(video_id)

            process = make_fake_process(
                stdout=str(tmp_path / f"{video_id}.mp4") + "\n",
            )

            def fake_communicate():
                # ファイル名確認中にキャンセルを要求する。
                application.cancel_requested.set()
                return process.communicate.return_value

            process.communicate.side_effect = fake_communicate
            return process

        download_calls.append(video_id)
        return make_fake_process(download=True)

    with (
        patch.object(gui, "download_yt_dlp", return_value=tmp_path / "yt-dlp.exe"),
        patch.object(gui, "download_deno", return_value=deno_path),
        patch.object(gui, "download_ffmpeg", return_value=ffmpeg_directory),
        patch.object(gui.subprocess, "Popen", side_effect=fake_popen),
    ):
        application.run_playlist_download(
            "https://www.youtube.com/playlist?list=test",
            720,
            tmp_path,
        )

    success, message = application.download_results.get_nowait()

    assert success is False
    assert message == "キャンセルしました。"

    # ファイル名確認は1本目だけで終了する。
    assert filename_calls == ["video001"]
    assert download_calls == []
    assert application.download_process is None

    assert application.download_process is None


def test_download_process_termination_requested_only_once() -> None:
    """同じプロセスへの終了要求が一度だけになることを確認する。"""
    application = object.__new__(gui.MediaDockGUI)

    application.download_process_lock = threading.Lock()
    application.download_process_termination_requested = False

    process = MagicMock()
    process.poll.return_value = None

    application.download_process = process

    with patch.object(
        application,
        "terminate_download_process",
    ) as terminate_mock:
        with application.download_process_lock:
            application.request_download_process_termination(process)
            application.request_download_process_termination(process)

    terminate_mock.assert_called_once_with(process)
    assert application.download_process_termination_requested is True


def test_download_process_termination_resets_for_new_process() -> None:
    """新しいプロセスでは終了要求を再び発行できることを確認する。"""
    application = object.__new__(gui.MediaDockGUI)

    application.download_process_lock = threading.Lock()
    application.download_process_termination_requested = False

    first_process = MagicMock()
    first_process.poll.return_value = None

    second_process = MagicMock()
    second_process.poll.return_value = None

    with patch.object(
        application,
        "terminate_download_process",
    ) as terminate_mock:
        with application.download_process_lock:
            application.download_process = first_process
            application.download_process_termination_requested = False

            application.request_download_process_termination(first_process)

            # 新しいプロセスの登録を再現する。
            application.download_process = second_process
            application.download_process_termination_requested = False

            application.request_download_process_termination(second_process)

    assert terminate_mock.call_count == 2

    assert terminate_mock.call_args_list[0].args == (first_process,)
    assert terminate_mock.call_args_list[1].args == (second_process,)

    assert application.download_process_termination_requested is True


def test_download_process_termination_is_thread_safe() -> None:
    """複数スレッドからの終了要求でも、終了処理は一度だけ実行する。"""
    application = object.__new__(gui.MediaDockGUI)

    application.download_process_lock = threading.Lock()
    application.download_process_termination_requested = False

    process = MagicMock()
    process.poll.return_value = None

    application.download_process = process

    start_event = threading.Event()
    errors = []

    def request_termination() -> None:
        try:
            start_event.wait(timeout=5)

            with application.download_process_lock:
                application.request_download_process_termination(process)
        except Exception as error:
            errors.append(error)

    with patch.object(
        application,
        "terminate_download_process",
    ) as terminate_mock:
        threads = [
            threading.Thread(target=request_termination)
            for _ in range(10)
        ]

        for thread in threads:
            thread.start()

        start_event.set()

        for thread in threads:
            thread.join(timeout=5)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []

    terminate_mock.assert_called_once_with(process)
    assert application.download_process_termination_requested is True


def test_playlist_auto_download_enabled() -> None:
    """プレイリスト取得後、自動ダウンロードONなら開始する。"""
    application = object.__new__(gui.MediaDockGUI)

    application.results = queue.Queue()
    application.results.put(
        (
            True,
            json.dumps(
                {
                    "type": "playlist",
                    "url": "https://www.youtube.com/playlist?list=test123",
                    "title": "テストプレイリスト",
                    "videos": [
                        {
                            "id": "video1",
                            "title": "テスト動画1",
                        }
                    ],
                },
                ensure_ascii=False,
            ),
        )
    )

    application.fetch_button = MagicMock()
    application.title_label = MagicMock()
    application.id_label = MagicMock()
    application.playlist_listbox = MagicMock()
    application.playlist_frame = MagicMock()
    application.quality_combo = MagicMock()
    application.status_label = MagicMock()
    application.download_button = MagicMock()
    application.auto_download_var = MagicMock()
    application.auto_download_var.get.return_value = True

    with (
        patch.object(application, "adjust_window_height"),
        patch.object(application, "on_quality_changed"),
        patch.object(application, "start_download") as download_mock,
    ):
        application.check_result()

    download_mock.assert_called_once_with()
    assert len(application.playlist_videos) == 1


def test_playlist_auto_download_disabled() -> None:
    """プレイリスト取得後、自動ダウンロードOFFなら開始しない。"""
    application = object.__new__(gui.MediaDockGUI)

    application.results = queue.Queue()
    application.results.put(
        (
            True,
            json.dumps(
                {
                    "type": "playlist",
                    "url": "https://www.youtube.com/playlist?list=test123",
                    "title": "テストプレイリスト",
                    "videos": [
                        {
                            "id": "video1",
                            "title": "テスト動画1",
                        }
                    ],
                },
                ensure_ascii=False,
            ),
        )
    )

    application.fetch_button = MagicMock()
    application.title_label = MagicMock()
    application.id_label = MagicMock()
    application.playlist_listbox = MagicMock()
    application.playlist_frame = MagicMock()
    application.quality_combo = MagicMock()
    application.status_label = MagicMock()
    application.download_button = MagicMock()
    application.auto_download_var = MagicMock()
    application.auto_download_var.get.return_value = False

    with (
        patch.object(application, "adjust_window_height"),
        patch.object(application, "on_quality_changed"),
        patch.object(application, "start_download") as download_mock,
    ):
        application.check_result()

    download_mock.assert_not_called()
    assert len(application.playlist_videos) == 1
    application.download_button.config.assert_called_with(state="normal")


def test_playlist_auto_download_with_no_videos() -> None:
    """動画0件のプレイリストでは自動ダウンロードを開始しない。"""
    application = object.__new__(gui.MediaDockGUI)

    application.results = queue.Queue()
    application.results.put(
        (
            True,
            json.dumps(
                {
                    "type": "playlist",
                    "url": "https://www.youtube.com/playlist?list=test123",
                    "title": "空のプレイリスト",
                    "videos": [],
                },
                ensure_ascii=False,
            ),
        )
    )

    application.fetch_button = MagicMock()
    application.title_label = MagicMock()
    application.id_label = MagicMock()
    application.playlist_listbox = MagicMock()
    application.playlist_frame = MagicMock()
    application.quality_combo = MagicMock()
    application.status_label = MagicMock()
    application.download_button = MagicMock()
    application.auto_download_var = MagicMock()
    application.auto_download_var.get.return_value = True

    with (
        patch.object(application, "adjust_window_height"),
        patch.object(application, "on_quality_changed"),
        patch.object(application, "start_download") as download_mock,
    ):
        application.check_result()

    download_mock.assert_not_called()
    assert application.playlist_videos == []
    application.download_button.config.assert_called_with(state="disabled")


def test_single_video_auto_download_enabled() -> None:
    """単体動画取得後、自動ダウンロードONなら開始する。"""
    application = object.__new__(gui.MediaDockGUI)

    application.results = queue.Queue()
    application.results.put(
        (
            True,
            json.dumps(
                [
                    "https://www.youtube.com/watch?v=test123",
                    "テスト動画",
                    "test123",
                    [1080, 720, 480],
                ],
                ensure_ascii=False,
            ),
        )
    )

    application.fetch_button = MagicMock()
    application.title_label = MagicMock()
    application.id_label = MagicMock()
    application.quality_combo = MagicMock()
    application.status_label = MagicMock()
    application.download_button = MagicMock()
    application.auto_download_var = MagicMock()
    application.auto_download_var.get.return_value = True

    with (
        patch.object(application, "on_quality_changed"),
        patch.object(application, "start_download") as download_mock,
    ):
        application.check_result()

    download_mock.assert_called_once_with()
    assert application.fetched_video_url == (
        "https://www.youtube.com/watch?v=test123"
    )
    application.download_button.config.assert_called_with(state="normal")
