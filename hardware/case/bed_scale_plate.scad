/*
 * bed_scale_plate.scad — 2dosumi ベッド下スケールプレート
 *
 * Raspberry Pi 4 + HX711 + 50kg半橋ロードセル×4 を内蔵する
 * 体重計型の一体プレート。ベッドの脚1本の下に敷いて使う。
 *
 * 構成パーツ (part 変数で切替):
 *   base     — 下皿。ロードセル4個・Pi 4・HX711 を搭載
 *   top      — 上蓋。四隅のロードセルのボタン4点だけに接触して浮く
 *   ring     — 脚受けリング。上蓋の天面にピンで固定(φ80mmまでの脚に対応)
 *   spacer   — 残り3本の脚用の同高スペーサー(3個印刷)
 *   assembly — 組立状態の確認用ビュー(印刷しない)
 *
 * 荷重経路: ベッドの脚 → 上蓋 → ボス×4 → ロードセルのボタン → ペデスタル → 床
 * 上蓋はベースの壁・Pi・HX711 のどこにも触れない(スカートは横ズレ防止のみ)。
 */

/* [部品選択] */
part = "assembly"; // [assembly, base, top, ring, spacer]

/* [全体寸法] */
base_outer = 168;   // ベース外形(一辺)。Bambu A1 mini (180角) 対応。上蓋は+7.8mm大きくなる
wall_t     = 3;     // 外壁厚
floor_t    = 3;     // 床厚
wall_h     = 25;    // 外壁高さ
corner_r   = 6;     // 外形コーナーR

/* [公差] */
cell_fit  = 0.3;    // ロードセルポケットの片側クリアランス
skirt_gap = 1.5;    // スカートとベース外壁の横クリアランス
pin_fit   = 0.2;    // リングピン穴の片側クリアランス

/* [ロードセル (50kg 半橋・体重計タイプ)] */
cell_w        = 34;    // セル本体の一辺
cell_h        = 7.6;   // セル全高
cell_inset    = 25;    // ベース外形コーナーからセル中心までの距離
pedestal_wh   = 44;    // ペデスタル(支持台)の一辺
pocket_wall_t = 2.4;   // セル位置決め壁の厚さ
pocket_wall_h = 4;     // セル位置決め壁の高さ
relief_w      = 24;    // セル中央下の逃げ(たわみ用)の一辺
relief_d      = 3;     // 逃げ深さ
wire_slot_w   = 8;     // セル配線用スロット幅

/* [トッププレート] */
top_underside = 27;    // 上蓋下面の高さ(Pi上空クリアランスを決める)
top_t         = 7;     // 上蓋板厚
skirt_t       = 2.4;   // スカート厚
skirt_drop    = 7;     // スカートが下面から下がる量
boss_d        = 16;    // ロードセルのボタンを押すボスの直径
boss_len      = 4;     // ボス長さ(接触面 z = top_underside - boss_len)
rib_t         = 3;     // 裏面リブ厚
rib_d         = 5;     // 裏面リブ深さ(Pi上空はリブなし)

/* [脚受けリング] */
ring_od     = 110;  // リング外径
ring_id     = 90;   // リング内径(φ80までの脚を受ける)
ring_h      = 5;    // リング高さ
ring_pin_d  = 5;    // 固定ピン径
ring_pin_h  = 3;    // 固定ピン長さ
ring_pin_bc = 100;  // ピン配置円直径

/* [Raspberry Pi 4] */
pi_l        = 85;
pi_w        = 56;
pi_hole_dx  = 58;    // 取付穴ピッチ X
pi_hole_dy  = 49;    // 取付穴ピッチ Y
pi_hole_off = 3.5;   // 基板端から穴中心まで
standoff_h  = 4;     // スタンドオフ高さ
standoff_od = 6.5;
standoff_id = 2.2;   // M2.5 セルフタップ下穴

/* [HX711] */
hx_l      = 34;      // 基板長辺
hx_w      = 21;      // 基板短辺
hx_wall_h = 4;       // 保持リブ高さ
hx_pos    = [46, 0]; // ベイ中心(長辺はY向きに配置)

/* [スペーサー] */
spacer_d          = 110;
spacer_dish_d     = 90;
spacer_dish_depth = 2;

/* [Hidden] */
$fn = 64;
eps = 0.01;

// 派生寸法
cc         = base_outer/2 - cell_inset;               // セル中心座標 (±cc, ±cc)
top_outer  = base_outer + 2*(skirt_gap + skirt_t);    // 上蓋外形
pocket_in  = cell_w + 2*cell_fit;
pocket_out = pocket_in + 2*pocket_wall_t;
// ペデスタル高さ: ボス接触面(top_underside - boss_len)からセル高+ボタン0.4mmを逆算
pedestal_h = top_underside - boss_len - cell_h - 0.4;
// スペーサー高さ: 本体の脚接地面(=上蓋天面)+皿深さ
spacer_h   = top_underside + top_t + spacer_dish_depth;
// Pi 4 は中央縦置き: 基板 56(X)×85(Y)、コネクタ長辺は -X(左壁)向き、
// USB/Ethernet の短辺は +Y(奥)向き、SDカードは -Y(手前)向き
slit_cy    = -pi_l/2 + 36;                            // 左壁スリット中心Y (USB-C〜audioを覆う)
slit_w     = 58;
slit_z     = 6;
pi_holes   = [for (hx = [-pi_hole_dy/2, pi_hole_dy/2],
                   hy = [-pi_l/2 + pi_hole_off, -pi_l/2 + pi_hole_off + pi_hole_dx])
                [hx, hy]];

// ---------- 汎用 ----------
module rsq(sx, sy, r = 3) offset(r) offset(-r) square([sx, sy], center = true);
module rbox(sx, sy, h, r = 3) linear_extrude(height = h) rsq(sx, sy, r);

// ---------- ベース ----------

// ロードセル支持台。原点=セル中心、配線スロットは +X 向き
module pedestal() {
    difference() {
        union() {
            rbox(pedestal_wh, pedestal_wh, pedestal_h, 4);
            // セル位置決め壁
            translate([0, 0, pedestal_h]) linear_extrude(pocket_wall_h)
                difference() {
                    rsq(pocket_out, pocket_out, 4);
                    rsq(pocket_in, pocket_in, 3);
                }
        }
        // セル中央下の逃げ(セルは外周5mm幅のリムで支持される)
        translate([0, 0, pedestal_h - relief_d])
            rbox(relief_w, relief_w, relief_d + pocket_wall_h + eps, 4);
        // 配線スロット(壁を貫通、上開放)
        translate([pocket_in/2 - 1, -wire_slot_w/2, pedestal_h])
            cube([pocket_wall_t + 2, wire_slot_w, pocket_wall_h + eps]);
    }
}

// HX711 保持ベイ。原点=ベイ中心、床上面に置く
module hx_bay() {
    in_x = hx_l + 0.8;
    in_y = hx_w + 0.8;
    difference() {
        linear_extrude(hx_wall_h)
            difference() {
                rsq(in_x + 4, in_y + 4, 3);
                rsq(in_x, in_y, 2);
            }
        // 両端のワイヤ開口
        for (sx = [-1, 1])
            translate([sx*(in_x/2 + 2), 0, hx_wall_h/2 + 0.5])
                cube([8, 14, hx_wall_h + 2], center = true);
    }
}

module base() {
    difference() {
        union() {
            // 床 + 外壁
            difference() {
                rbox(base_outer, base_outer, wall_h, corner_r);
                translate([0, 0, floor_t])
                    rbox(base_outer - 2*wall_t, base_outer - 2*wall_t,
                         wall_h, max(1, corner_r - wall_t));
            }
            // ペデスタル×4(配線スロットが中央側を向くよう回転)
            for (sx = [-1, 1], sy = [-1, 1])
                translate([sx*cc, sy*cc, 0])
                    rotate([0, 0, sx > 0 ? 180 : 0]) pedestal();
            // Pi スタンドオフ
            for (p = pi_holes)
                translate([p[0], p[1], floor_t])
                    cylinder(d = standoff_od, h = standoff_h);
            // HX711 ベイ(長辺Y向き)
            translate([hx_pos[0], hx_pos[1], floor_t]) rotate([0, 0, 90]) hx_bay();
        }
        // スタンドオフ下穴(M2.5 セルフタップ)
        for (p = pi_holes)
            translate([p[0], p[1], floor_t + standoff_h - 5.5])
                cylinder(d = standoff_id, h = 6);
        // 左側面ケーブルスリット(USB-C電源・HDMI。上開放でブリッジ不要)
        translate([-base_outer/2 - 1, slit_cy - slit_w/2, slit_z])
            cube([wall_t + 2, slit_w, wall_h]);
        // 背面予備スリット(ブザー等)
        translate([-6, base_outer/2 - wall_t - 1, slit_z])
            cube([12, wall_t + 2, wall_h]);
        // ベントスロット(右側面+前面)
        for (vy = [-30, -10, 10, 30])
            translate([base_outer/2 - (wall_t + 2)/2, vy - 2, 8])
                cube([wall_t + 2, 4, 12]);
        for (vx = [-30, -10, 10, 30])
            translate([vx - 2, -base_outer/2 - 1, 8])
                cube([4, wall_t + 2, 12]);
        // HX711 結束バンド用スロット(床貫通)
        for (sx = [-1, 1])
            translate([hx_pos[0] + sx*(hx_w/2 + 5) - 1.5, hx_pos[1] - 4, -1])
                cube([3, 8, floor_t + 2]);
    }
}

// ---------- トッププレート ----------

module ribs() {
    difference() {
        intersection() {
            translate([0, 0, top_underside - rib_d])
                linear_extrude(rib_d + eps) union() {
                    for (a = [45, -45])
                        rotate([0, 0, a]) square([280, rib_t], center = true);
                    square([rib_t, 170], center = true);
                    square([170, rib_t], center = true);
                    // Pi両脇のフランクリブ(脚荷重を四隅へ流すメインビーム)
                    for (s = [-1, 1]) {
                        translate([s*(pi_w/2 + 8), 0])
                            square([rib_t, 170], center = true);
                        translate([0, s*(pi_l/2 + 8.5)])
                            square([170, rib_t], center = true);
                    }
                }
            rbox(base_outer - 2*wall_t - 4, base_outer - 2*wall_t - 4,
                 100, corner_r);
        }
        // Pi 上空はリブ禁止(クリアランス確保)
        translate([-pi_w/2 - 5, -pi_l/2 - 5, top_underside - rib_d - 1])
            cube([pi_w + 10, pi_l + 10, rib_d + 2]);
    }
}

module top_plate() {
    difference() {
        union() {
            // 天板スラブ
            translate([0, 0, top_underside])
                rbox(top_outer, top_outer, top_t, corner_r + 2);
            // スカート(横ズレ・ホコリ防止。上下方向はフリー)
            translate([0, 0, top_underside - skirt_drop])
                linear_extrude(skirt_drop + eps)
                    difference() {
                        rsq(top_outer, top_outer, corner_r + 2);
                        rsq(base_outer + 2*skirt_gap, base_outer + 2*skirt_gap,
                            corner_r + 1);
                    }
            // ロードセルボタンを押すボス×4
            for (sx = [-1, 1], sy = [-1, 1])
                translate([sx*cc, sy*cc, top_underside - boss_len])
                    cylinder(d = boss_d, h = boss_len + eps);
            ribs();
        }
        // 脚受けリング用ピン穴×3
        for (a = [90, 210, 330])
            rotate([0, 0, a])
                translate([ring_pin_bc/2, 0,
                           top_underside + top_t - ring_pin_h - 2*pin_fit])
                    cylinder(d = ring_pin_d + 2*pin_fit,
                             h = ring_pin_h + 2*pin_fit + eps);
    }
}

// ---------- 脚受けリング ----------
module leg_ring() {
    difference() {
        cylinder(d = ring_od, h = ring_h);
        translate([0, 0, -1]) cylinder(d = ring_id, h = ring_h + 2);
    }
    for (a = [90, 210, 330])
        rotate([0, 0, a])
            translate([ring_pin_bc/2, 0, -ring_pin_h])
                cylinder(d = ring_pin_d, h = ring_pin_h + eps);
}

// ---------- スペーサー ----------
module spacer() {
    difference() {
        cylinder(d = spacer_d, h = spacer_h);
        translate([0, 0, spacer_h - spacer_dish_depth])
            cylinder(d = spacer_dish_d, h = spacer_dish_depth + 1);
    }
}

// ---------- 組立ビュー用モック ----------
module cell_mock() {
    color("silver") {
        rbox(cell_w, cell_w, cell_h, 5);
        // ボタン(上蓋ボスとの接触点。プレビューのZファイティング防止に0.1mm短く)
        translate([0, 0, cell_h])
            cylinder(d = 12,
                     h = (top_underside - boss_len) - (pedestal_h + cell_h) - 0.1);
    }
}

module assembly() {
    color("#546e7a") base();
    color("#90caf9", 0.45) top_plate();
    // リングは表示用に0.15mm浮かせる(天面と同一平面だと描画が乱れるため)
    color("#ef9a9a", 0.7) translate([0, 0, top_underside + top_t + 0.15]) leg_ring();
    for (sx = [-1, 1], sy = [-1, 1])
        translate([sx*cc, sy*cc, pedestal_h]) cell_mock();
    color("green") translate([-pi_w/2, -pi_l/2, floor_t + standoff_h])
        cube([pi_w, pi_l, 1.4]);
    // 最背高部品(USB/Ethernetコネクタ 16mm)のモック
    color("lightgray") translate([-pi_w/2 + 2, pi_l/2 - 18, floor_t + standoff_h + 1.4])
        cube([pi_w - 4, 18, 16]);
    color("darkgreen") translate([hx_pos[0] - hx_w/2, hx_pos[1] - hx_l/2, floor_t + 1])
        cube([hx_w, hx_l, 1.6]);
}

// ---------- 出力(印刷パーツは印刷向きに配置) ----------
if (part == "base")
    base();
else if (part == "top")
    translate([0, 0, top_underside + top_t]) rotate([180, 0, 0]) top_plate();
else if (part == "ring")
    translate([0, 0, ring_h]) rotate([180, 0, 0]) leg_ring();
else if (part == "spacer")
    spacer();
else if (part == "section")
    // セル中心線(y=-cc)で切った断面。ボス接触とPi上空クリアランス確認用
    intersection() {
        assembly();
        translate([-500, -cc, -1]) cube([1000, 1000, 100]);
    }
else
    assembly();
