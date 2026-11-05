# SatelliteCreator

自然文の要求（何を観測・通信したいか、どの軌道で、何年動かすか、予算）から、**小型衛星（CubeSat 級）の構想設計**を作り、シミュレーションで検証した案だけを返すツールを目指すプロジェクトです。姉妹プロジェクト [RocketCreater](https://github.com/masatoshibukawa/RocketCreater)（要求からロケットを設計）と同じ考え方で作ります。

- 状態：立ち上げ直後（2026-11-05）
- ライセンス：MIT

## 目指す流れ

1. 要求を定量化する（軌道、ミッション期間、ペイロードの電力・質量・データ量、指向精度、予算）
2. 実在の衛星・部品カタログ（バス、太陽電池、バッテリー、通信機、姿勢制御機器）から構成を選ぶ
3. 電力・質量・データ・熱・軌道寿命・通信リンクの収支を計算して検証する
4. 合格した構成だけを、部品表・収支表・図つきで返す

## English summary

SatelliteCreator turns a plain-language mission request into a verified small-satellite
(CubeSat-class) concept design: requirements are quantified, components are chosen from a
sourced catalog, and power, mass, data, thermal, orbit-lifetime and link budgets are computed
before any design is shown. Sister project of RocketCreater. MIT licensed.
