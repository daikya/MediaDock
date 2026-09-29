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
        self.fetched_video_url: str | None = None
        self.cancel_requested = threading.Event()
        self.download_process: subprocess.Popen[str] | None = None
        self.download_process_lock = threading.Lock()
        self.yt_dlp_update_checked = False

        self.application_directory = get_application_directory()
        self.settings_path = self.application_directory / "settings.json"

        self.output_directory = Path.home() / "Downloads"
        self.window_x: int | None = None
        self.window_y: int | None = None

        if self.settings_path.is_file():
            try:
                settings = json.loads(
                    self.settings_path.read_text(encoding="utf-8")
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

        window_width = 640
        window_height = 540

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

        self.fetch_button = ttk.Button(
            frame,
            text="動画情報を取得",
            command=self.fetch_video_info,
        )
        self.fetch_button.pack(anchor="w")

        self.status_label = ttk.Label(frame, text="動画URLを入力してください。")
        self.status_label.pack(anchor="w", pady=(15, 5))

        self.title_label = ttk.Label(frame, text="タイトル: -", wraplength=590)
        self.title_label.pack(anchor="w", pady=5)

        self.id_label = ttk.Label(frame, text="動画ID: -")
        self.id_label.pack(anchor="w", pady=5)

        ttk.Label(frame, text="画質").pack(anchor="w", pady=(10, 5))

        self.quality_combo = ttk.Combobox(
            frame,
            state="disabled",
            values=[],
            width=15,
        )

        self.quality_combo.pack(anchor="w")

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

    def close_window(self) -> None:
        """ウィンドウ位置を保存して終了する。"""
        settings = {
            "output_directory": str(self.output_directory.resolve()),
            "window_x": self.root.winfo_x(),
            "window_y": self.root.winfo_y(),
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

    def fetch_video_info(self) -> None:
        """別スレッドで動画情報を取得する。"""
        video_url = self.url_entry.get().strip()

        if not video_url:
            self.status_label.config(text="動画URLを入力してください。")
            return

        self.fetch_button.config(state="disabled")
        self.download_button.config(state="disabled")
        self.fetched_video_url = None
        self.status_label.config(text="動画情報を取得しています...")
        self.title_label.config(text="タイトル: -")
        self.id_label.config(text="動画ID: -")

        self.quality_combo.config(state="disabled", values=[])
        self.quality_combo.set("")

        thread = threading.Thread(
            target=self.run_yt_dlp,
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

        video_url, title, video_id, available_heights = json.loads(message)
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

        threading.Thread(
            target=self.run_download,
            args=(video_url, selected_height, output_directory),
            daemon=True,
        ).start()

        self.root.after(100, self.check_download_result)

    def cancel_download(self) -> None:
        """ダウンロードのキャンセルを要求する。"""
        self.cancel_requested.set()
        self.cancel_button.config(state="disabled")
        self.status_label.config(text="キャンセル処理中...")

        with self.download_process_lock:
            process = self.download_process

        if process is not None and process.poll() is None:
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

                if self.cancel_requested.is_set():
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
            self.status_label.config(text="ダウンロードに失敗しました。")

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
