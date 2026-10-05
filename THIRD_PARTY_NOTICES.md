# Third-Party Notices

MediaDockは、動作に必要な以下の外部ソフトウェアを利用します。

これらのソフトウェアはMediaDock本体には含まれておらず、必要になった際に各配布元から自動的にダウンロードされます。

各ソフトウェアには、それぞれのライセンス条件が適用されます。

## yt-dlp

MediaDockは動画情報の取得および動画のダウンロードにyt-dlpを利用します。

- Project: yt-dlp
- Website: https://github.com/yt-dlp/yt-dlp
- License: The Unlicense

yt-dlpの公式実行ファイルには、別のライセンスが適用される第三者コンポーネントが含まれています。
詳細については、yt-dlpプロジェクトのLICENSEおよびTHIRD_PARTY_LICENSES.txtを参照してください。

- License:
  https://github.com/yt-dlp/yt-dlp/blob/master/LICENSE
- Third-party licenses:
  https://github.com/yt-dlp/yt-dlp/blob/master/THIRD_PARTY_LICENSES.txt

## Deno

MediaDockは、yt-dlpによる一部サイトの処理に必要なJavaScriptランタイムとしてDenoを利用します。

- Project: Deno
- Website: https://github.com/denoland/deno
- License: MIT License
- License information:
  https://github.com/denoland/deno/blob/main/LICENSE.md

## FFmpeg

MediaDockは、動画と音声の結合などのメディア処理にFFmpegを利用します。

MediaDockが自動取得するWindows向けFFmpegは、Gyan.devが提供するFFmpeg Essentials Buildです。

- Project: FFmpeg
- Website: https://ffmpeg.org/
- Windows build provider:
  https://www.gyan.dev/ffmpeg/builds/
- Build license: GNU General Public License version 3 (GPLv3)
- FFmpeg license information:
  https://ffmpeg.org/legal.html

## MediaDock

MediaDock本体はMIT Licenseで公開されています。

MediaDockのMIT Licenseは、上記の第三者ソフトウェアには適用されません。
各第三者ソフトウェアには、それぞれのライセンス条件が適用されます。
