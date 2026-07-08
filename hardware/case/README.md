# ベッド下スケールプレート(3Dプリントケース)

Raspberry Pi 4 + HX711 + 50kg半橋ロードセル×4 を内蔵する体重計型プレート。
ベッドの脚1本の下に敷き、脚にかかる荷重の変化でベッド復帰を検知する。

設計ソースは [bed_scale_plate.scad](bed_scale_plate.scad)(OpenSCAD、全寸法パラメトリック)。
STLは `stl/`、プレビュー画像は `img/` にある。

## 仕組み(荷重経路)

```
ベッドの脚
  → 脚受けリング付きの上蓋(top_plate + leg_ring)
  → 裏面のボス×4 → ロードセルのボタン×4
  → ペデスタル → 下皿(base_plate) → 床
```

上蓋はロードセルのボタン4点**だけ**に接触して浮いている。外周スカートは
横ズレ・ホコリ防止用で、下皿の壁とは上下方向に2mmの隙間があり荷重を邪魔しない。
Pi・HX711は下皿に固定され、上蓋裏面とは2.6mm以上のクリアランスがある。

## パーツと印刷

| STL | 個数 | サイズ | 備考 |
| --- | --- | --- | --- |
| `stl/base_plate.stl` | 1 | 168×168×25mm | 下皿。そのままの向きで印刷 |
| `stl/top_plate.stl` | 1 | 175.8×175.8×14mm | 上蓋。天面を下にした印刷向きでエクスポート済み |
| `stl/leg_ring.stl` | 1 | φ110×8mm | 脚受けリング(φ80までの脚に対応) |
| `stl/leg_spacer.stl` | 3 | φ110×36mm | 残り3本の脚用スペーサー(本体と同じ高さ34mm+皿2mm) |

- **Bambu A1 mini(180×180mm)で全パーツ印刷可**(最大175.8mm角)
- 材料: **PETG推奨**(PLA+でも可)。常時荷重がかかるため
- 壁 4〜6周、インフィル **40%以上**(ペデスタル部が潰れないように)
- サポート不要(全パーツその向きのまま)

## 必要部品

- 50kg 半橋ロードセル ×4(体重計タイプ、34×34mm)
- HX711 モジュール ×1
- Raspberry Pi 4 ×1
- M2.5×6mm タッピングネジ ×4(Pi固定)
- 結束バンド ×1(HX711固定)
- 瞬間接着剤 少量(脚受けリングのピン固定)

## 組立手順

1. 下皿の四隅ポケットにロードセルを置く(ボタン面を上、配線は中央向きのスロットから出す)
2. ロードセル4本の配線をHX711へ。結線はルート [README.md](../../README.md) の
   「4 load cell wiring」の表の通り(E+/E-/A+/A- の合成、HX711→Pi は GPIO5/6)
3. HX711 を中央のベイにはめ、床の貫通スロットに結束バンドを通して固定
4. Pi 4 をスタンドオフに M2.5 ネジで固定(縦置き: USB-C/HDMI辺が左壁、USB/Ethernetが奥向き)。
   USB-C 電源ケーブルは左側面スリットから外へ
5. 上蓋をかぶせる(スカートが下皿の壁の外側に重なる)
6. 脚受けリングのピン3本に接着剤を付け、上蓋天面の穴に差し込む
7. ベッドの脚1本をリングの内側に載せ、残り3本の脚にスペーサーを敷く
8. `python3 -m twodosumi calibrate-zero` → `calibrate-scale` で校正(ルートREADME参照)

## 寸法をいじりたいとき

`.scad` 先頭のパラメータを変更して再エクスポート:

- `base_outer` — プレート外形(現在168mm=A1 mini対応。大きいプリンタなら192等に拡大可)
- `ring_id` — 脚がφ80を超える場合に拡大(`ring_od`・`spacer_d` も合わせて)
- `top_underside` — Pi上空クリアランス(ヒートシンク搭載時は+数mm)
- `cell_w` / `cell_h` — ロードセルの実寸が違う場合

```powershell
$scad = "C:\Program Files\OpenSCAD\openscad.com"
& $scad -o stl\base_plate.stl -D 'part="base"'   bed_scale_plate.scad
& $scad -o stl\top_plate.stl  -D 'part="top"'    bed_scale_plate.scad
& $scad -o stl\leg_ring.stl   -D 'part="ring"'   bed_scale_plate.scad
& $scad -o stl\leg_spacer.stl -D 'part="spacer"' bed_scale_plate.scad
```

組立確認は `part="assembly"`、断面確認は `part="section"` をOpenSCADのGUIで表示。

## 注意

- 本体の全高は34mm。**必ず残り3本の脚にもスペーサー(または同厚の板)を敷いて**
  ベッドを水平に保つこと
- 定格は 50kg×4=200kg(半橋合成)。通常のシングルベッド+成人1人で問題ないが、
  片脚への集中荷重が大きい重いベッドでは脚の位置をリング中央に正しく合わせること
- 印刷品はクリープ(常時荷重での変形)があるため、検知値が徐々にドリフトしたら
  Web UI からゼロ校正をやり直す
