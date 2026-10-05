# MediaDock

YouTube / TVerの動画取得を支援するWindows向けデスクトップアプリ。

## 特徴

- Windows向けデスクトップアプリ
- yt-dlpを利用した動画取得
- 必要な外部ツールを利用時に自動取得
  - yt-dlp
  - Deno
  - FFmpeg
- GUIによる操作
- 画質選択
- ダウンロード進捗表示
- キャンセル対応

## 動作環境

- Windows 10 / 11
- インターネット接続環境

## インストール

GitHub Releasesから `MediaDock-v1.0.0-win64.zip` をダウンロードしてください。

ダウンロードしたZIPファイルを任意の場所へ展開し、`MediaDock.exe` を起動してください。

必要な外部ツールは、動画情報の取得やダウンロードを行った際に自動的に準備されます。

### Windows Defender SmartScreenについて

初回起動時に、Microsoft Defender SmartScreenによって「WindowsによってPCが保護されました」と表示される場合があります。

GitHub ReleasesからダウンロードしたMediaDockであることを確認したうえで、「詳細情報」をクリックし、「実行」を選択してください。

## 使い方

1. `MediaDock.exe` を起動
2. 動画URLを入力
3. 「動画情報を取得」をクリック
4. 画質を選択
5. 「ダウンロード開始」をクリック

## 注意事項

- YouTube利用時はブラウザCookieを利用します。
- Cookie取得にはFirefoxを使用します。
- 動画サイト側の仕様変更により動作しなくなる場合があります。
- yt-dlpの更新により改善される場合があります。
- ダウンロードした動画の利用については、各サービスの利用規約および権利関係を確認してください。

## License

MediaDock本体はMIT Licenseで公開されています。

利用している外部ソフトウェアのライセンスについては、[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) を参照してください。
