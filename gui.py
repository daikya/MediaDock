"""MediaDockのGUI。"""

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import urllib.error
import urllib.request
import zipfile
from collections import deque
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from urllib.parse import parse_qs, urlparse


def is_youtube_playlist_url(url: str) -> bool:
    """YouTubeのプレイリストURLかどうかを判定する。"""
    parsed = urlparse(url)

    hostname = (parsed.hostname or "").lower()

    if hostname not in (
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
    ):
        return False

    query = parse_qs(parsed.query)
    playlist_ids = query.get("list", [])

    if not any(playlist_id.strip() for playlist_id in playlist_ids):
        return False

    return parsed.path in ("/playlist", "/watch")


def get_application_directory() -> Path:
    """MediaDock本体があるフォルダーを取得する。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parent


def get_resource_path(relative_path: str) -> Path:
    """PyInstallerに格納したリソースのパスを取得する。"""
    if getattr(sys, "frozen", False):
        base_directory = Path(sys._MEIPASS)
    else:
        base_directory = Path(__file__).resolve().parent

    return base_directory / relative_path


def get_subprocess_creationflags() -> int:
    """Windowsで子プロセスのコンソールウィンドウを表示しない。"""
    if os.name == "nt":
        return subprocess.CREATE_NO_WINDOW

    return 0


def get_format_size(video_format: dict) -> int | None:
    """動画形式のファイルサイズを取得する。"""
    for key in ("filesize", "filesize_approx"):
        size = video_format.get(key)

        if isinstance(size, (int, float)) and not isinstance(size, bool):
            if size > 0:
                return int(size)

    return None


def format_file_size(size: int | None) -> str:
    """ファイルサイズを読みやすい単位で表示する。"""
    if size is None:
        return "不明"

    if size >= 1024**3:
        return f"約 {size / 1024**3:.2f} GB"

    if size >= 1024**2:
        return f"約 {size / 1024**2:.1f} MB"

    if size >= 1024:
        return f"約 {size / 1024:.1f} KB"

    return f"約 {size} B"


def get_selected_formats_size(video_info: dict) -> int | None:
    """yt-dlpが選択した形式の合計ファイルサイズを取得する。"""
    requested_formats = video_info.get("requested_formats")

    if isinstance(requested_formats, list) and requested_formats:
        total_size = 0

        for video_format in requested_formats:
            size = get_format_size(video_format)

            if size is None:
                return None

            total_size += size

        return total_size

    return get_format_size(video_info)


def download_yt_dlp(application_directory: Path) -> Path:
    """yt-dlp.exeがなければ公式配布元からダウンロードする。"""
    tools_directory = application_directory / "tools"
    yt_dlp_path = tools_directory / "yt-dlp.exe"

    if yt_dlp_path.is_file():
        return yt_dlp_path

    tools_directory.mkdir(parents=True, exist_ok=True)

    download_url = (
        "https://github.com/yt-dlp/yt-dlp-nightly-builds/"
        "releases/latest/download/yt-dlp.exe"
    )
    temporary_path = tools_directory / "yt-dlp.exe.download"

    try:
        urllib.request.urlretrieve(
            download_url,
            temporary_path,
        )
        temporary_path.replace(yt_dlp_path)
    except (OSError, urllib.error.URLError) as error:
        temporary_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"yt-dlp.exeをダウンロードできませんでした: {error}"
        ) from error

    return yt_dlp_path


def download_deno(application_directory: Path) -> Path:
    """deno.exeがなければ公式配布元からダウンロードする。"""
    tools_directory = application_directory / "tools"
    deno_path = tools_directory / "deno.exe"

    if deno_path.is_file():
        return deno_path

    tools_directory.mkdir(parents=True, exist_ok=True)

    download_url = (
        "https://github.com/denoland/deno/releases/latest/download/"
        "deno-x86_64-pc-windows-msvc.zip"
    )
    zip_path = tools_directory / "deno.zip.download"
    extract_directory = tools_directory / "deno.download"

    try:
        urllib.request.urlretrieve(
            download_url,
            zip_path,
        )

        extract_directory.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path) as archive:
            archive.extract("deno.exe", extract_directory)

        extracted_deno_path = extract_directory / "deno.exe"
        extracted_deno_path.replace(deno_path)
    except (OSError, urllib.error.URLError, zipfile.BadZipFile, KeyError) as error:
        raise RuntimeError(
            f"deno.exeをダウンロードできませんでした: {error}"
        ) from error
    finally:
        zip_path.unlink(missing_ok=True)

        if extract_directory.is_dir():
            extracted_deno_path = extract_directory / "deno.exe"
            extracted_deno_path.unlink(missing_ok=True)

            try:
                extract_directory.rmdir()
            except OSError:
                pass

    return deno_path


def download_ffmpeg(application_directory: Path) -> Path:
    """FFmpegがなければWindows用Essentialsビルドをダウンロードする。"""
    tools_directory = application_directory / "tools"
    ffmpeg_directory = tools_directory / "ffmpeg"
    ffmpeg_path = ffmpeg_directory / "ffmpeg.exe"
    ffprobe_path = ffmpeg_directory / "ffprobe.exe"

    if ffmpeg_path.is_file() and ffprobe_path.is_file():
        return ffmpeg_directory

    tools_directory.mkdir(parents=True, exist_ok=True)

    download_url = (
        "https://www.gyan.dev/ffmpeg/builds/"
        "ffmpeg-release-essentials.zip"
    )
    zip_path = tools_directory / "ffmpeg.zip.download"
    extract_directory = tools_directory / "ffmpeg.download"

    try:
        urllib.request.urlretrieve(
            download_url,
            zip_path,
        )

        extract_directory.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(extract_directory)

        extracted_ffmpeg_path = next(
            extract_directory.glob("*/bin/ffmpeg.exe")
        )
        extracted_ffprobe_path = next(
            extract_directory.glob("*/bin/ffprobe.exe")
        )

        ffmpeg_directory.mkdir(parents=True, exist_ok=True)

        extracted_ffmpeg_path.replace(ffmpeg_path)
        extracted_ffprobe_path.replace(ffprobe_path)
    except (
        OSError,
        urllib.error.URLError,
        zipfile.BadZipFile,
        StopIteration,
    ) as error:
        raise RuntimeError(
            f"FFmpegをダウンロードできませんでした: {error}"
        ) from error
    finally:
        zip_path.unlink(missing_ok=True)
        shutil.rmtree(extract_directory, ignore_errors=True)

    return ffmpeg_directory


class MediaDockGUI:
    """動画情報を取得して表示する画面。"""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("MediaDock")
        self.root.iconbitmap(
            default=get_resource_path("assets/mediadock.ico")
        )

        self.results: queue.Queue[tuple[bool, str]] = queue.Queue()
        self.download_results: queue.Queue[tuple[bool, str]] = queue.Queue()
        self.download_progress: queue.Queue[float] = queue.Queue()
        self.playlist_download_status: queue.Queue[
            tuple[int, int, str]
        ] = queue.Queue()
        self.size_results: queue.Queue[tuple[str, int, int | None]] = queue.Queue()
        self.playlist_size_results: queue.Queue[
            tuple[str, int, int, int, int]
        ] = queue.Queue()
        self.playlist_size_pending: set[tuple[str, int]] = set()
        self.playlist_size_cache: dict[
            tuple[str, int], tuple[int, int, int]
        ] = {}
        self.playlist_size_check_scheduled = False
        self.size_check_scheduled = False
        self.size_cache: dict[tuple[str, int], int | None] = {}
        self.size_pending: set[tuple[str, int]] = set()
        self.fetched_video_url: str | None = None
        self.playlist_videos: list[dict] = []
        self.cancel_requested = threading.Event()
        self.download_process: subprocess.Popen[str] | None = None
        self.download_process_lock = threading.Lock()
        self.download_process_termination_requested = False
        self.yt_dlp_update_checked = False

        self.application_directory = get_application_directory()
        self.settings_path = self.application_directory / "settings.json"
        self.auto_download_enabled = False

        self.output_directory = Path.home() / "Downloads"
        self.window_x: int | None = None
        self.window_y: int | None = None

        if self.settings_path.is_file():
            try:
                settings = json.loads(
                    self.settings_path.read_text(encoding="utf-8")
                )
                self.auto_download_enabled = (
                    settings.get("auto_download", False) is True
                )
                saved_directory = settings.get("output_directory")

                if saved_directory:
                    saved_directory_path = Path(saved_directory)

                    if saved_directory_path.is_dir():
                        self.output_directory = saved_directory_path

                window_x = settings.get("window_x")
                window_y = settings.get("window_y")

                if isinstance(window_x, int) and isinstance(window_y, int):
                    self.window_x = window_x
                    self.window_y = window_y

            except (OSError, ValueError, TypeError):
                pass

        self.root.update_idletasks()

        self.normal_window_width = 640
        self.normal_window_height = 540

        window_width = self.normal_window_width
        window_height = self.normal_window_height

        if self.window_x is None or self.window_y is None:
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()

            self.window_x = (screen_width - window_width) // 2
            self.window_y = (screen_height - window_height) // 2

        self.root.geometry(
            f"{window_width}x{window_height}+{self.window_x}+{self.window_y}"
        )

        frame = ttk.Frame(root, padding=20)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="動画URL").pack(anchor="w")

        self.url_entry = ttk.Entry(frame)
        self.url_entry.pack(fill="x", pady=(5, 10))

        # 動画情報取得ボタンと自動ダウンロード設定
        fetch_frame = ttk.Frame(frame)
        fetch_frame.pack(anchor="w")

        self.fetch_button = ttk.Button(
            fetch_frame,
            text="動画情報を取得",
            command=self.fetch_video_info,
        )
        self.fetch_button.pack(side="left")

        self.auto_download_var = tk.BooleanVar(
            value=self.auto_download_enabled
        )

        self.auto_download_check = ttk.Checkbutton(
            fetch_frame,
            text="取得後に自動ダウンロード",
            variable=self.auto_download_var,
        )
        self.auto_download_check.pack(side="left", padx=(15, 0))

        self.status_label = ttk.Label(frame, text="動画URLを入力してください。")
        self.status_label.pack(anchor="w", pady=(15, 5))

        self.title_label = ttk.Label(frame, text="タイトル: -", wraplength=590)
        self.title_label.pack(anchor="w", pady=5)

        self.id_label = ttk.Label(frame, text="動画ID: -")
        self.id_label.pack(anchor="w", pady=5)
        # プレイリスト内の動画一覧
        self.playlist_frame = ttk.Frame(frame)

        self.playlist_listbox = tk.Listbox(
            self.playlist_frame,
            height=5,
            exportselection=False,
        )

        self.playlist_scrollbar = ttk.Scrollbar(
            self.playlist_frame,
            orient="vertical",
            command=self.playlist_listbox.yview,
        )

        self.playlist_listbox.config(
            yscrollcommand=self.playlist_scrollbar.set
        )

        self.playlist_listbox.pack(
            side="left",
            fill="both",
            expand=True,
        )

        self.playlist_scrollbar.pack(
            side="right",
            fill="y",
        )
        ttk.Label(frame, text="画質").pack(anchor="w", pady=(10, 5))

        self.quality_combo = ttk.Combobox(
            frame,
            state="disabled",
            values=[],
            width=15,
        )

        self.quality_combo.pack(anchor="w")
        self.quality_combo.bind("<<ComboboxSelected>>", self.on_quality_changed)
        self.file_size_label = ttk.Label(frame, text="推定ファイルサイズ: -")
        self.file_size_label.pack(anchor="w", pady=(5, 0))
        ttk.Label(frame, text="保存先フォルダー").pack(
            anchor="w",
            pady=(15, 5),
        )

        output_frame = ttk.Frame(frame)
        output_frame.pack(fill="x")

        self.output_directory_var = tk.StringVar(
            value=str(self.output_directory)
        )

        self.output_entry = ttk.Entry(
            output_frame,
            textvariable=self.output_directory_var,
            state="readonly",
        )
        self.output_entry.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(0, 10),
        )

        self.browse_button = ttk.Button(
            output_frame,
            text="参照...",
            command=self.select_output_directory,
        )
        self.browse_button.pack(side="right")
        self.download_button = ttk.Button(
            frame,
            text="ダウンロード開始",
            command=self.start_download,
            state="disabled",
        )
        self.download_button.pack(anchor="w", pady=(20, 0))
        self.cancel_button = ttk.Button(
            frame,
            text="キャンセル",
            command=self.cancel_download,
            state="disabled",
        )
        self.cancel_button.pack(anchor="w", pady=(5, 0))
        self.progress_bar = ttk.Progressbar(
            frame,
            orient="horizontal",
            mode="determinate",
            maximum=100,
        )
        self.progress_bar.pack(fill="x", pady=(15, 5))

        self.progress_label = ttk.Label(
            frame,
            text="現在のファイル: 0%",
        )
        self.progress_label.pack(anchor="w")
        self.url_entry.focus_set()
        self.root.protocol("WM_DELETE_WINDOW", self.close_window)

    def adjust_window_height(self, playlist_visible: bool) -> None:
        """プレイリスト表示に応じてウィンドウの高さを調整する。"""
        self.root.update_idletasks()

        if playlist_visible:
            desired_height = max(
                self.normal_window_height,
                self.root.winfo_reqheight(),
            )
        else:
            desired_height = self.normal_window_height

        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            work_area = wintypes.RECT()

            if ctypes.windll.user32.SystemParametersInfoW(
                0x0030, 0, ctypes.byref(work_area), 0
            ):
                available_top = work_area.top
                available_bottom = work_area.bottom
            else:
                available_top = 0
                available_bottom = self.root.winfo_screenheight()
        else:
            available_top = 0
            available_bottom = self.root.winfo_screenheight()

        available_height = available_bottom - available_top
        target_height = min(desired_height, available_height)

        current_x = self.root.winfo_x()
        current_y = self.root.winfo_y()

        target_y = max(
            available_top,
            min(current_y, available_bottom - target_height),
        )

        self.root.geometry(
            f"{self.normal_window_width}x{target_height}"
            f"+{current_x}+{target_y}"
        )

    def close_window(self) -> None:
        """ウィンドウ位置を保存して終了する。"""
        settings = {
            "output_directory": str(self.output_directory.resolve()),
            "window_x": self.root.winfo_x(),
            "window_y": self.root.winfo_y(),
            "auto_download": self.auto_download_var.get(),
        }

        try:
            self.settings_path.write_text(
                json.dumps(
                    settings,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass

        self.root.destroy()

    def select_output_directory(self) -> None:
        """保存先フォルダーを選択し、設定を保存する。"""
        selected_directory = filedialog.askdirectory(
            parent=self.root,
            title="保存先フォルダーを選択",
            initialdir=str(self.output_directory),
            mustexist=True,
        )

        if not selected_directory:
            return

        new_directory = Path(selected_directory)

        if not new_directory.is_dir():
            messagebox.showerror(
                "MediaDock",
                "選択したフォルダーが存在しません。",
                parent=self.root,
            )
            return

        try:
            self.settings_path.write_text(
                json.dumps(
                    {
                        "output_directory": str(new_directory.resolve()),
                        "window_x": self.root.winfo_x(),
                        "window_y": self.root.winfo_y(),
                        "auto_download": self.auto_download_var.get(),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError as error:
            messagebox.showerror(
                "MediaDock",
                f"保存先の設定を保存できませんでした。\n{error}",
                parent=self.root,
            )
            return

        self.output_directory = new_directory
        self.output_directory_var.set(str(new_directory))
        self.status_label.config(text="保存先フォルダーを変更しました。")

    def on_quality_changed(self, event: tk.Event | None = None) -> None:
        """画質が変更されたときの処理。"""
        if self.playlist_videos:
            playlist_url = self.fetched_video_url
            selected_quality = self.quality_combo.get()

            if not playlist_url or not selected_quality:
                return

            selected_height = int(selected_quality.removesuffix("p"))
            cache_key = (playlist_url, selected_height)

            if cache_key in self.playlist_size_cache:
                total_size, known_count, video_count = (
                    self.playlist_size_cache[cache_key]
                )
                self.show_playlist_size(
                    total_size, known_count, video_count
                )
                return

            self.file_size_label.config(
                text="合計推定ファイルサイズ: 取得中..."
            )

            if cache_key not in self.playlist_size_pending:
                self.playlist_size_pending.add(cache_key)

                threading.Thread(
                    target=self.run_playlist_size_estimation,
                    args=(playlist_url, selected_height),
                    daemon=True,
                ).start()

            if not self.playlist_size_check_scheduled:
                self.playlist_size_check_scheduled = True
                self.root.after(100, self.check_playlist_size_result)

            return
        video_url = self.fetched_video_url
        selected_quality = self.quality_combo.get()

        if not video_url or not selected_quality:
            self.file_size_label.config(text="推定ファイルサイズ: -")
            return

        selected_height = int(selected_quality.removesuffix("p"))
        cache_key = (video_url, selected_height)

        if cache_key in self.size_cache:
            size = self.size_cache[cache_key]
            self.file_size_label.config(
                text=f"推定ファイルサイズ: {format_file_size(size)}"
            )
            return

        self.file_size_label.config(text="推定ファイルサイズ: 取得中...")

        if cache_key not in self.size_pending:
            self.size_pending.add(cache_key)

            thread = threading.Thread(
                target=self.run_size_estimation,
                args=(video_url, selected_height),
                daemon=True,
            )
            thread.start()

        if not self.size_check_scheduled:
            self.size_check_scheduled = True
            self.root.after(100, self.check_size_result)

    def run_size_estimation(
        self,
        video_url: str,
        selected_height: int,
    ) -> None:
        """yt-dlpが選択した形式の推定ファイルサイズを取得する。"""
        try:
            yt_dlp_path = self.application_directory / "tools" / "yt-dlp.exe"
            deno_path = self.application_directory / "tools" / "deno.exe"

            is_youtube = (
                "youtube.com" in video_url or "youtu.be" in video_url
            )

            if is_youtube:
                format_selector = (
                    f"bv*[vcodec^=avc1][height<={selected_height}]"
                    f"+ba[acodec^=mp4a]/"
                    f"b[vcodec^=avc1][acodec^=mp4a]"
                    f"[height<={selected_height}]"
                )
            else:
                format_selector = (
                    f"bv*[height<={selected_height}]"
                    f"+ba/b[height<={selected_height}]"
                )

            command = [
                str(yt_dlp_path),
                "--ignore-config",
            ]

            if is_youtube:
                command.extend([
                    "--no-js-runtimes",
                    "--js-runtimes",
                    f"deno:{deno_path}",
                    "--cookies-from-browser",
                    "firefox",
                ])

            command.extend([
                "-f",
                format_selector,
                "--dump-single-json",
                "--skip-download",
                video_url,
            ])

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                creationflags=get_subprocess_creationflags(),
            )

            size = None

            if result.returncode == 0:
                video_info = json.loads(result.stdout)
                size = get_selected_formats_size(video_info)

            self.size_results.put((video_url, selected_height, size))

        except (OSError, ValueError, TypeError):
            self.size_results.put((video_url, selected_height, None))

    def show_playlist_size(
        self,
        total_size: int,
        known_count: int,
        video_count: int,
    ) -> None:
        """プレイリストの推定ファイルサイズを表示する。"""
        expected_count = len(self.playlist_videos)

        if (
            expected_count > 0
            and known_count == expected_count
            and video_count == expected_count
        ):
            self.file_size_label.config(
                text=(
                    "合計推定ファイルサイズ: "
                    f"{format_file_size(total_size)}"
                )
            )
        elif known_count > 0:
            self.file_size_label.config(
                text=(
                    "合計推定ファイルサイズ: "
                    f"{format_file_size(total_size)}"
                    f"（{known_count}/{expected_count}本、取得分のみ）"
                )
            )
        else:
            self.file_size_label.config(
                text="合計推定ファイルサイズ: 不明"
            )

    def check_playlist_size_result(self) -> None:
        """プレイリストのサイズ取得結果をGUIへ反映する。"""
        while True:
            try:
                (
                    playlist_url,
                    selected_height,
                    total_size,
                    known_count,
                    video_count,
                ) = self.playlist_size_results.get_nowait()
            except queue.Empty:
                break

            cache_key = (playlist_url, selected_height)
            self.playlist_size_pending.discard(cache_key)
            self.playlist_size_cache[cache_key] = (
                total_size,
                known_count,
                video_count,
            )

            if (
                self.playlist_videos
                and self.fetched_video_url == playlist_url
                and self.quality_combo.get()
                == f"{selected_height}p"
            ):
                self.show_playlist_size(
                    total_size,
                    known_count,
                    video_count,
                )

        if self.playlist_size_pending:
            self.root.after(100, self.check_playlist_size_result)
        else:
            self.playlist_size_check_scheduled = False

    def run_playlist_size_estimation(
        self,
        playlist_url: str,
        selected_height: int,
    ) -> None:
        """プレイリスト全体の推定ファイルサイズを取得する。"""
        try:
            yt_dlp_path = self.application_directory / "tools" / "yt-dlp.exe"
            deno_path = self.application_directory / "tools" / "deno.exe"

            format_selector = (
                f"bv*[vcodec^=avc1][height<={selected_height}]"
                f"+ba[acodec^=mp4a]/"
                f"b[vcodec^=avc1][acodec^=mp4a]"
                f"[height<={selected_height}]"
            )

            command = [
                str(yt_dlp_path),
                "--ignore-config",
                "--no-js-runtimes",
                "--js-runtimes",
                f"deno:{deno_path}",
                "--cookies-from-browser",
                "firefox",
                "--yes-playlist",
                "--ignore-errors",
                "-f",
                format_selector,
                "--dump-json",
                "--skip-download",
                playlist_url,
            ]

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                creationflags=get_subprocess_creationflags(),
            )

            total_size = 0
            known_count = 0
            video_count = 0

            for line in result.stdout.splitlines():
                if not line.strip():
                    continue

                video_info = json.loads(line)
                video_count += 1

                size = get_selected_formats_size(video_info)

                if size is not None:
                    total_size += size
                    known_count += 1

            self.playlist_size_results.put(
                (
                    playlist_url,
                    selected_height,
                    total_size,
                    known_count,
                    video_count,
                )
            )

        except (OSError, ValueError, TypeError):
            self.playlist_size_results.put(
                (playlist_url, selected_height, 0, 0, 0)
            )

    def check_size_result(self) -> None:
        """推定ファイルサイズの取得結果をGUIに反映する。"""
        while True:
            try:
                video_url, selected_height, size = self.size_results.get_nowait()
            except queue.Empty:
                break

            cache_key = (video_url, selected_height)

            self.size_pending.discard(cache_key)
            self.size_cache[cache_key] = size

            if video_url != self.fetched_video_url:
                continue

            if self.quality_combo.get() != f"{selected_height}p":
                continue

            self.file_size_label.config(
                text=f"推定ファイルサイズ: {format_file_size(size)}"
            )

        if self.size_pending:
            self.root.after(100, self.check_size_result)
        else:
            self.size_check_scheduled = False

    def fetch_video_info(self) -> None:
        """別スレッドで動画情報を取得する。"""
        video_url = self.url_entry.get().strip()

        if not video_url:
            self.status_label.config(text="動画URLを入力してください。")
            return

        self.fetch_button.config(state="disabled")
        self.download_button.config(state="disabled")
        self.fetched_video_url = None
        self.playlist_videos = []
        self.playlist_listbox.delete(0, tk.END)
        self.playlist_frame.pack_forget()
        self.adjust_window_height(playlist_visible=False)
        self.size_cache.clear()
        self.status_label.config(text="動画情報を取得しています...")
        self.title_label.config(text="タイトル: -")
        self.id_label.config(text="動画ID: -")

        self.quality_combo.config(state="disabled", values=[])
        self.quality_combo.set("")
        self.file_size_label.config(text="推定ファイルサイズ: -")
        if is_youtube_playlist_url(video_url):
            target = self.run_playlist_info
        else:
            target = self.run_yt_dlp

        thread = threading.Thread(
            target=target,
            args=(video_url,),
            daemon=True,
        )
        thread.start()

        self.root.after(100, self.check_result)

    def update_yt_dlp(self, yt_dlp_path: Path) -> None:
        """1起動につき1回だけyt-dlpの更新を確認する。"""
        if self.yt_dlp_update_checked:
            return

        self.yt_dlp_update_checked = True

        try:
            subprocess.run(
                [
                    str(yt_dlp_path),
                    "--ignore-config",
                    "-U",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                creationflags=get_subprocess_creationflags(),
            )
        except OSError:
            pass

    def run_playlist_info(self, playlist_url: str) -> None:
        """YouTubeプレイリストの動画一覧を取得する。"""
        try:
            yt_dlp_path = download_yt_dlp(self.application_directory)
            deno_path = download_deno(self.application_directory)
        except RuntimeError as error:
            self.results.put((False, str(error)))
            return

        self.update_yt_dlp(yt_dlp_path)

        command = [
            str(yt_dlp_path),
            "--ignore-config",
            "--no-js-runtimes",
            "--js-runtimes",
            f"deno:{deno_path}",
            "--cookies-from-browser",
            "firefox",
            "--flat-playlist",
            "--dump-single-json",
            "--skip-download",
            playlist_url,
        ]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                creationflags=get_subprocess_creationflags(),
            )
        except OSError as error:
            self.results.put(
                (False, f"プレイリスト情報の取得に失敗しました: {error}")
            )
            return

        if result.returncode != 0:
            message = result.stderr.strip() or "原因不明のエラーです。"
            self.results.put(
                (False, f"プレイリスト情報の取得に失敗しました: {message}")
            )
            return

        try:
            playlist_info = json.loads(result.stdout)
        except json.JSONDecodeError:
            self.results.put(
                (False, "プレイリスト情報の解析に失敗しました。")
            )
            return

        entries = playlist_info.get("entries") or []

        videos = [
            {
                "id": entry.get("id"),
                "title": entry.get("title") or "タイトル不明",
            }
            for entry in entries
            if isinstance(entry, dict) and entry.get("id")
        ]

        payload = {
            "type": "playlist",
            "url": playlist_url,
            "title": playlist_info.get("title") or "タイトル不明",
            "videos": videos,
        }

        self.results.put(
            (True, json.dumps(payload, ensure_ascii=False))
        )

    def run_yt_dlp(self, video_url: str) -> None:
        """yt-dlpを実行し、結果をキューに渡す。"""
        try:
            yt_dlp_path = download_yt_dlp(self.application_directory)
        except RuntimeError as error:
            self.results.put((False, str(error)))
            return

        self.update_yt_dlp(yt_dlp_path)

        try:
            deno_path = download_deno(self.application_directory)
        except RuntimeError as error:
            self.results.put((False, str(error)))
            return

        command = [
            str(yt_dlp_path),
            "--ignore-config",
        ]

        if "youtube.com" in video_url or "youtu.be" in video_url:
            if not deno_path.is_file():
                self.results.put((False, f"deno.exeが見つかりません: {deno_path}"))
                return

            command.extend(
                [
                    "--no-js-runtimes",
                    "--js-runtimes",
                    f"deno:{deno_path}",
                    "--cookies-from-browser",
                    "firefox",
                ]
            )

        command.extend(
            [
                "--dump-single-json",
                "--skip-download",
                video_url,
            ]
        )

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                creationflags=get_subprocess_creationflags(),
            )
        except OSError as error:
            self.results.put((False, f"yt-dlpの起動に失敗しました: {error}"))
            return

        if result.returncode != 0:
            message = result.stderr.strip() or "原因不明のエラーです。"
            self.results.put((False, f"動画情報の取得に失敗しました: {message}"))
            return

        try:
            video_info = json.loads(result.stdout)
        except json.JSONDecodeError:
            self.results.put((False, "動画情報の解析に失敗しました。"))
            return

        title = video_info.get("title", "不明")
        video_id = video_info.get("id", "不明")

        resolutions = set()

        for video_format in video_info.get("formats", []):
            height = video_format.get("height")
            video_codec = video_format.get("vcodec")

            if isinstance(height, int) and video_codec not in (None, "none"):
                resolutions.add(height)

        available_heights = sorted(resolutions, reverse=True)

        self.results.put(
            (
                True,
                json.dumps(
                    [video_url, title, video_id, available_heights],
                    ensure_ascii=False,
                ),
            )
        )

    def check_result(self) -> None:
        """動画情報の取得結果をGUIに反映する。"""
        try:
            success, message = self.results.get_nowait()
        except queue.Empty:
            self.root.after(100, self.check_result)
            return

        self.fetch_button.config(state="normal")

        if not success:
            self.status_label.config(text=message)
            return


        result = json.loads(message)

        if isinstance(result, dict) and result.get("type") == "playlist":
            self.fetched_video_url = result["url"]
            self.playlist_videos = result["videos"]

            playlist_title = result["title"]
            video_count = len(self.playlist_videos)

            self.title_label.config(
                text=f"プレイリスト名: {playlist_title}"
            )
            self.id_label.config(
                text=f"動画件数: {video_count}件"
            )
            self.playlist_listbox.delete(0, tk.END)

            for index, video in enumerate(self.playlist_videos, start=1):
                title = video.get("title") or "タイトル不明"
                self.playlist_listbox.insert(
                    tk.END,
                    f"{index}. {title}",
                )

            self.playlist_frame.pack(
                fill="x",
                pady=(5, 10),
                before=self.quality_combo,
            )
            self.adjust_window_height(playlist_visible=True)
            self.status_label.config(
                text="プレイリスト情報を取得しました。"
            )

            # プレイリスト全体に適用する画質の上限
            quality_values = [
                "1080p",
                "720p",
                "480p",
                "360p",
                "240p",
                "144p",
            ]

            self.quality_combo.config(
                values=quality_values,
                state="readonly",
            )
            self.quality_combo.current(0)
            self.on_quality_changed()

            if video_count > 0:
                self.download_button.config(state="normal")
            else:
                self.download_button.config(state="disabled")

            return

        video_url, title, video_id, available_heights = result
        self.fetched_video_url = video_url

        self.title_label.config(text=f"タイトル: {title}")
        self.id_label.config(text=f"動画ID: {video_id}")

        if not available_heights:
            self.status_label.config(text="選択可能な画質がありません。")
            return

        quality_values = [
            f"{height}p"
            for height in available_heights
        ]

        self.quality_combo.config(
            values=quality_values,
            state="readonly",
        )
        self.quality_combo.current(0)
        self.status_label.config(text="動画情報を取得しました。")
        self.download_button.config(state="normal")

        self.on_quality_changed()

        if self.auto_download_var.get():
            self.start_download()

    def start_download(self) -> None:
        """GUIで選択した条件を使ってダウンロードを開始する。"""
        video_url = self.url_entry.get().strip()
        selected_quality = self.quality_combo.get()

        if not video_url or not selected_quality:
            messagebox.showerror(
                "MediaDock",
                "動画情報と画質を確認してください。",
                parent=self.root,
            )
            return

        if video_url != self.fetched_video_url:
            messagebox.showerror(
                "MediaDock",
                "動画URLが変更されています。\n動画情報を再取得してください。",
                parent=self.root,
            )
            return

        if not self.output_directory.is_dir():
            messagebox.showerror(
                "MediaDock",
                "保存先フォルダーが存在しません。",
                parent=self.root,
            )
            return

        selected_height = int(selected_quality.removesuffix("p"))
        output_directory = self.output_directory

        self.fetch_button.config(state="disabled")
        self.download_button.config(state="disabled")
        self.browse_button.config(state="disabled")
        self.quality_combo.config(state="disabled")
        self.cancel_requested.clear()
        self.cancel_button.config(state="normal")
        self.status_label.config(text="ダウンロードを実行しています...")
        self.progress_bar["value"] = 0
        self.progress_label.config(text="現在のファイル: 0%")

        if self.playlist_videos:
            download_target = self.run_playlist_download
        else:
            download_target = self.run_download

        threading.Thread(
            target=download_target,
            args=(video_url, selected_height, output_directory),
            daemon=True,
        ).start()

        self.root.after(100, self.check_download_result)


    def terminate_download_process(
        self,
        process: subprocess.Popen[str],
    ) -> None:
        """実行中の外部プロセスの終了を要求する。"""
        if process.poll() is not None:
            return

        try:
            if os.name == "nt":
                subprocess.Popen(
                    [
                        "taskkill",
                        "/PID",
                        str(process.pid),
                        "/T",
                        "/F",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=get_subprocess_creationflags(),
                )
            else:
                process.terminate()
        except OSError:
            # 終了要求と同時にプロセスが終了する場合がある。
            pass

    def request_download_process_termination(
        self,
        process: subprocess.Popen[str],
    ) -> None:
        """同じプロセスへの終了要求を一度だけ発行する。

        呼び出し元は download_process_lock を取得していること。
        """
        if self.download_process is not process:
            return

        if self.download_process_termination_requested:
            return

        if process.poll() is not None:
            return

        self.download_process_termination_requested = True
        self.terminate_download_process(process)

    def cancel_download(self) -> None:
        """ダウンロードのキャンセルを要求する。"""
        self.cancel_requested.set()
        self.cancel_button.config(state="disabled")
        self.status_label.config(text="キャンセル処理中...")

        with self.download_process_lock:
            process = self.download_process

            if process is not None:
                self.request_download_process_termination(process)

    def run_playlist_download(
        self,
        playlist_url: str,
        selected_height: int,
        output_directory: Path,
    ) -> None:
        """プレイリスト内の動画を順番にダウンロードする。"""
        try:
            yt_dlp_path = download_yt_dlp(self.application_directory)
            deno_path = download_deno(self.application_directory)
            ffmpeg_path = download_ffmpeg(self.application_directory)
        except RuntimeError as error:
            self.download_results.put((False, str(error)))
            return

        if not deno_path.is_file():
            self.download_results.put(
                (False, f"deno.exeが見つかりません。\n{deno_path}")
            )
            return

        if not (ffmpeg_path / "ffmpeg.exe").is_file():
            self.download_results.put(
                (False, f"ffmpeg.exeが見つかりません。\n{ffmpeg_path}")
            )
            return

        videos = list(self.playlist_videos)

        if not videos:
            self.download_results.put(
                (False, "プレイリストに動画がありません。")
            )
            return

        total_count = len(videos)
        downloaded_count = 0
        skipped_count = 0
        failed_count = 0
        failed_videos: list[str] = []

        for index, video in enumerate(videos, start=1):
            self.playlist_download_status.put(
                (index, total_count, "確認中")
            )
            if self.cancel_requested.is_set():
                self.download_results.put(
                    (False, "キャンセルしました。")
                )
                return

            video_id = video.get("id")

            if not video_id:
                continue

            video_url = f"https://www.youtube.com/watch?v={video_id}"

            format_selector = (
                f"bv*[vcodec^=avc1][height<={selected_height}]"
                f"+ba[acodec^=mp4a]/"
                f"b[vcodec^=avc1][acodec^=mp4a]"
                f"[height<={selected_height}]"
            )

            base_command = [
                str(yt_dlp_path),
                "--ignore-config",
                "--no-js-runtimes",
                "--js-runtimes",
                f"deno:{deno_path}",
                "--cookies-from-browser",
                "firefox",
                "--no-playlist",
                "--ffmpeg-location",
                str(ffmpeg_path),
                "-f",
                format_selector,
                "--merge-output-format",
                "mp4",
                "-o",
                str(output_directory / "%(title)s [%(id)s].%(ext)s"),
            ]

            filename_command = base_command + [
                "--simulate",
                "--print",
                "filename",
                "--encoding",
                "utf-8",
                video_url,
            ]

            try:
                with subprocess.Popen(
                    filename_command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=get_subprocess_creationflags(),
                ) as process:
                    with self.download_process_lock:
                        self.download_process = process
                        self.download_process_termination_requested = False

                        if self.cancel_requested.is_set():
                            self.request_download_process_termination(process)

                    stdout, stderr = process.communicate()
                    filename_result = subprocess.CompletedProcess(
                        args=filename_command,
                        returncode=process.returncode,
                        stdout=stdout,
                        stderr=stderr,
                    )

            except OSError as error:
                if self.cancel_requested.is_set():
                    self.download_results.put(
                        (False, "キャンセルしました。")
                    )
                    return

                failed_count += 1
                failed_videos.append(
                    f"{index}/{total_count}本目: "
                    f"{video.get('title', 'タイトル不明')}"
                    f"（ファイル名確認エラー: {error}）"
                )
                continue

            finally:
                with self.download_process_lock:
                    self.download_process = None

            if self.cancel_requested.is_set():
                self.download_results.put(
                    (False, "キャンセルしました。")
                )
                return

            if filename_result.returncode != 0:
                failed_count += 1
                error_detail = (
                    filename_result.stderr.strip()[-500:]
                    or f"終了コード: {filename_result.returncode}"
                )
                failed_videos.append(
                    f"{index}/{total_count}本目: "
                    f"{video.get('title', 'タイトル不明')}"
                    f"（ファイル名取得失敗: {error_detail}）"
                )
                continue

            filenames = [
                line.strip()
                for line in filename_result.stdout.splitlines()
                if line.strip()
            ]

            if len(filenames) != 1:
                failed_count += 1
                failed_videos.append(
                    f"{index}/{total_count}本目: "
                    f"{video.get('title', 'タイトル不明')}"
                    "（保存予定ファイル名を一意に取得できませんでした）"
                )
                continue

            expected_file = Path(filenames[0])

            if expected_file.is_file():
                skipped_count += 1
                self.playlist_download_status.put(
                    (index, total_count, "既存ファイルをスキップ")
                )
                continue

            self.playlist_download_status.put(
                (index, total_count, "ダウンロード中")
            )

            download_command = base_command + [
                "--newline",
                "--progress-template",
                "download:MEDIADOCK_PROGRESS:%(progress._percent_str)s",
                "--encoding",
                "utf-8",
                "--convert-thumbnails",
                "jpg",
                "--embed-thumbnail",
                video_url,
            ]

            log_lines = deque(maxlen=30)

            try:
                with subprocess.Popen(
                    download_command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=get_subprocess_creationflags(),
                ) as process:
                    with self.download_process_lock:
                        self.download_process = process
                        self.download_process_termination_requested = False

                        if self.cancel_requested.is_set():
                            self.request_download_process_termination(process)

                    assert process.stdout is not None

                    for line in process.stdout:
                        log_lines.append(line.rstrip())

                        match = re.search(
                            r"MEDIADOCK_PROGRESS:\s*([\d.]+)%",
                            line,
                        )

                        if match:
                            percent = float(match.group(1))
                            self.download_progress.put(percent)

                    return_code = process.wait()

            except OSError as error:
                if self.cancel_requested.is_set():
                    self.download_results.put(
                        (False, "キャンセルしました。")
                    )
                    return

                failed_count += 1
                failed_videos.append(
                    f"{index}/{total_count}本目: "
                    f"{video.get('title', 'タイトル不明')}"
                    f"（ダウンロード実行エラー: {error}）"
                )
                continue

            finally:
                with self.download_process_lock:
                    self.download_process = None

            if self.cancel_requested.is_set():
                self.download_results.put(
                    (False, "キャンセルしました。")
                )
                return

            if return_code != 0:
                failed_count += 1
                error_log = "\n".join(log_lines)[-500:]

                failed_videos.append(
                    f"{index}/{total_count}本目: "
                    f"{video.get('title', 'タイトル不明')}"
                    f"（終了コード: {return_code}）\n"
                    f"{error_log}"
                )
                continue

            downloaded_count += 1

        if failed_count == 0:
            result_title = "プレイリストのダウンロードが完了しました。"
            success = True
        elif downloaded_count + skipped_count > 0:
            result_title = "プレイリストの処理が一部失敗しました。"
            success = False
        else:
            result_title = "プレイリストのダウンロードがすべて失敗しました。"
            success = False

        result_message = (
            f"{result_title}\n"
            f"対象動画数: {total_count}本\n"
            f"ダウンロード成功: {downloaded_count}本\n"
            f"既存ファイルをスキップ: {skipped_count}本\n"
            f"失敗: {failed_count}本"
        )

        if failed_videos:
            result_message += (
                "\n\n失敗した動画:\n"
                + "\n".join(failed_videos)
            )

        self.download_results.put((success, result_message))

    def run_download(
        self,
        video_url: str,
        selected_height: int,
        output_directory: Path,
    ) -> None:
        """別スレッドでファイル確認とダウンロードを実行する。"""
        try:
            yt_dlp_path = download_yt_dlp(self.application_directory)
        except RuntimeError as error:
            self.download_results.put((False, str(error)))
            return

        deno_path = self.application_directory / "tools" / "deno.exe"
        try:
            ffmpeg_path = download_ffmpeg(self.application_directory)
        except RuntimeError as error:
            self.download_results.put((False, str(error)))
            return

        if not (ffmpeg_path / "ffmpeg.exe").is_file():
            self.download_results.put(
                (False, f"ffmpeg.exeが見つかりません。\n{ffmpeg_path}")
            )
            return

        base_command = [
            str(yt_dlp_path),
            "--ignore-config",
        ]

        if "youtube.com" in video_url or "youtu.be" in video_url:
            if not deno_path.is_file():
                self.download_results.put(
                    (False, f"deno.exeが見つかりません。\n{deno_path}")
                )
                return

            base_command.extend(
                [
                    "--no-js-runtimes",
                    "--js-runtimes",
                    f"deno:{deno_path}",
                    "--cookies-from-browser",
                    "firefox",
                ]
            )

        if "youtube.com" in video_url or "youtu.be" in video_url:
            format_selector = (
                f"bv*[vcodec^=avc1][height<={selected_height}]"
                f"+ba[acodec^=mp4a]/"
                f"b[vcodec^=avc1][acodec^=mp4a][height<={selected_height}]"
            )
        else:
            format_selector = (
                f"bv*[height<={selected_height}]"
                f"+ba/b[height<={selected_height}]"
            )

        base_command.extend(
            [
                "--ffmpeg-location",
                str(ffmpeg_path),
                "-f",
                format_selector,
                "--merge-output-format",
                "mp4",
                "-o",
                str(output_directory / "%(title)s [%(id)s].%(ext)s"),
            ]
        )

        filename_command = base_command + [
            "--simulate",
            "--print",
            "filename",
            "--encoding",
            "utf-8",
            video_url,
        ]

        try:
            filename_result = subprocess.run(
                filename_command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                creationflags=get_subprocess_creationflags(),
            )

            if self.cancel_requested.is_set():
                self.download_results.put(
                    (False, "キャンセルしました。")
                )
                return

            if filename_result.returncode != 0:
                self.download_results.put(
                    (
                        False,
                        "保存予定のファイル名を取得できませんでした。\n"
                        + filename_result.stderr.strip()[-1500:],
                    )
                )
                return

            filenames = [
                line.strip()
                for line in filename_result.stdout.splitlines()
                if line.strip()
            ]

            if len(filenames) != 1:
                self.download_results.put(
                    (False, "保存予定のファイル名を一意に取得できませんでした。")
                )
                return

            expected_file = Path(filenames[0])

            if expected_file.is_file():
                self.download_results.put(
                    (
                        True,
                        f"既存ファイルが見つかったためスキップしました。\n"
                        f"{expected_file}",
                    )
                )
                return

            download_command = base_command + [
                "--newline",
                "--progress-template",
                "download:MEDIADOCK_PROGRESS:%(progress._percent_str)s",
                "--encoding",
                "utf-8",
                "--convert-thumbnails",
                "jpg",
                "--embed-thumbnail",
                video_url,
            ]

            log_lines = deque(maxlen=30)

            with subprocess.Popen(
                download_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=get_subprocess_creationflags(),
            ) as process:
                with self.download_process_lock:
                    self.download_process = process
                    self.download_process_termination_requested = False

                    if self.cancel_requested.is_set():
                        self.request_download_process_termination(process)

                assert process.stdout is not None

                for line in process.stdout:
                    log_lines.append(line.rstrip())

                    match = re.search(
                        r"MEDIADOCK_PROGRESS:\s*([\d.]+)%",
                        line,
                    )

                    if match:
                        percent = float(match.group(1))
                        self.download_progress.put(percent)

                return_code = process.wait()

            with self.download_process_lock:
                self.download_process = None

        except OSError as error:
            with self.download_process_lock:
                self.download_process = None

            if self.cancel_requested.is_set():
                self.download_results.put(
                    (False, "キャンセルしました。")
                )
                return

            self.download_results.put(
                (False, f"ダウンロード処理を実行できませんでした。\n{error}")
            )
            return

        if self.cancel_requested.is_set():
            self.download_results.put(
                (False, "キャンセルしました。")
            )
            return

        if return_code == 0:
            self.download_results.put(
                (True, f"ダウンロードが完了しました。\n{expected_file}")
            )
        else:
            error_log = "\n".join(log_lines)[-1500:]

            self.download_results.put(
                (
                    False,
                    "ダウンロードに失敗しました。\n"
                    f"終了コード: {return_code}\n"
                    + error_log,
                )
            )

    def check_download_result(self) -> None:
        """ダウンロードの進捗と結果をGUIに反映する。"""
        while True:
            try:
                index, total_count, status = (
                    self.playlist_download_status.get_nowait()
                )
            except queue.Empty:
                break

            self.status_label.config(
                text=(
                    "プレイリストを処理しています "
                    f"（{index}/{total_count}本目・{status}）"
                )
            )

            if status in ("確認中", "ダウンロード中"):
                self.progress_bar["value"] = 0
                self.progress_label.config(
                    text="現在のファイル: 0%"
                )
        while True:
            try:
                percent = self.download_progress.get_nowait()
            except queue.Empty:
                break

            self.progress_bar["value"] = percent
            self.progress_label.config(
                text=f"現在のファイル: {percent:.1f}%"
            )

        try:
            success, message = self.download_results.get_nowait()
        except queue.Empty:
            self.root.after(100, self.check_download_result)
            return

        self.fetch_button.config(state="normal")
        self.download_button.config(state="normal")
        self.browse_button.config(state="normal")
        self.quality_combo.config(state="readonly")
        self.cancel_button.config(state="disabled")

        if message == "キャンセルしました。":
            self.status_label.config(text=message)
            self.progress_label.config(text="キャンセル")
            messagebox.showinfo(
                "MediaDock",
                message,
                parent=self.root,
            )

        elif success:
            if message.startswith("ダウンロードが完了しました。"):
                self.progress_bar["value"] = 100
                self.progress_label.config(text="処理完了")

            self.status_label.config(text=message.splitlines()[0])

            messagebox.showinfo(
                "MediaDock",
                message,
                parent=self.root,
            )
        else:
            self.status_label.config(text=message.splitlines()[0])

            if message.startswith("プレイリストの処理が一部失敗しました。"):
                messagebox.showwarning(
                    "MediaDock",
                    message,
                    parent=self.root,
                )
            else:
                messagebox.showerror(
                    "MediaDock",
                    message,
                    parent=self.root,
                )


def main() -> None:
    root = tk.Tk()
    MediaDockGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
