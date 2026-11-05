# SatelliteCreator

人工衛星への要求を受け取り、衛星の開発工程に沿って対話で要求を詰め、計算で検証した**設計書**を出力するツールを目指すプロジェクトです。対象は CubeSat 1U〜6U、地球低軌道です。姉妹プロジェクト [RocketCreater](https://github.com/masatoshibukawa/RocketCreater)（要求からロケットを設計）と同じ考え方で作り、最終的には統合します。

- 状態：開発中。要求の整理、工程の確認、設計の核、軌道、質量、熱の計算、設計書の枠組み、画面まで動きます。質量と熱は 3U だけで、OPT-CUBE の機器構成を目安にした暫定値です。電力、回線、構造の計算は未実装で、設計書の該当箇所は「未計算」と表示します
- ライセンス：MIT

## 目指す流れ

1. 曖昧な要求を、対話で「確定、仮定、未定」に整理して定量化する
2. JAXA のシステム設計標準 JERG-2-100 の審査（MDR、SRR、SDR、PDR、CDR）を関門にして、工程を順に進める
3. 軌道、構造、熱、電源、通信、データ処理、姿勢制御を部品から設計し、計算で検証する
4. 衛星設計コンテストの解析書の章立てで設計書を出力する

衛星設計コンテストの受賞作の解析書を正解データとして、ミッション要求に対応する設計値が得られることをテストで確かめます。解析書の PDF はこのリポジトリに含めず、抽出した数値と出典だけを置きます。

## 開発

```bash
uv sync
uv run pytest
```

画面と API をまとめて起動するには、次を実行します。画面は http://127.0.0.1:3010 で開きます。

```bash
./scripts/dev.sh
```

画面には Node 18.18 以上が必要です。`scripts/dev.sh` は `~/.local/opt/node22/bin` の Node を使います。別の場所の Node を使うときは、`SATELLITECREATOR_NODE_BIN` にその `bin` を指定してください。

設計結果をロケット側へ渡す `launch_request.json` は、画面の保存ボタンか次のコマンドで出力します。実例は `examples/opt_cube/` にあります。

```bash
uv run python -m satellitecreator.launch_request --prompt "$(cat examples/opt_cube/request.txt)" --name OPT-CUBE --output launch_request.json
```

反復設計はコマンドでも動きます。`DesignAgent` を実装すれば、エージェントを追加、交換できます。既定では規則で動く熱のエージェントを使い、API を呼びません。Claude のエージェントは次のように有効にします。検査が不合格のときだけ、1 回の反復で最大 3 回、Claude Haiku 5.5 を呼びます。

```bash
SATELLITECREATOR_USE_CLAUDE=1 SATELLITECREATOR_ENV_FILE=../RocketCreater/.env ./scripts/dev.sh
```

```bash
uv run python -m satellitecreator.iteration --prompt "高度 400 km、軌道傾斜角 51.6 度の 3U CubeSat。消費電力 20 W"
```

API は認証なしで動くため、ローカルでの利用を前提に `127.0.0.1` に限定しています。

## English summary

SatelliteCreator turns satellite requirements into a verified design document for 1U-6U
CubeSats in low Earth orbit. Ambiguous requirements are refined interactively, the work passes
through the JAXA JERG-2-100 review gates, and every number comes from code with a source.
Award-winning reports from Japan's Satellite Design Contest serve as reference data.
Sister project of RocketCreater. MIT licensed.
