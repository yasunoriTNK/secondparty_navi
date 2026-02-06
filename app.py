import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any

import pandas as pd
import pydeck as pdk
import streamlit as st


# =========================
# Settings / Constants
# =========================
APP_TITLE = "Shibuya Re:balance Navi（2次会一発予約）"

# 渋谷駅あたり（デモ用の現在地固定）
DEFAULT_LAT = 35.6580
DEFAULT_LON = 139.7016

DATA_PATH = Path(__file__).parent / "data" / "restaurants.json"

ARRIVAL_OPTIONS = [
    ("今すぐ", 0),
    ("15分後", 15),
    ("30分後", 30),
    ("60分後", 60),
]


# =========================
# Utilities
# =========================
def haversine_km(lat1, lon1, lat2, lon2) -> float:
    """2点間距離(km)"""
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


@dataclass
class Restaurant:
    id: str
    name: str
    area: str
    genre: List[str]
    price_yen: int
    rating: float
    smoking: str  # "no" | "yes" | "separated"
    capacity: int
    lat: float
    lon: float
    photo_url: str
    address: str
    open: str
    fee_yen: int
    description: str

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Restaurant":
        return Restaurant(
            id=d["id"],
            name=d["name"],
            area=d.get("area", ""),
            genre=list(d.get("genre", [])),
            price_yen=int(d.get("price_yen", 0)),
            rating=float(d.get("rating", 0.0)),
            smoking=d.get("smoking", "no"),
            capacity=int(d.get("capacity", 0)),
            lat=float(d.get("lat", 0.0)),
            lon=float(d.get("lon", 0.0)),
            photo_url=d.get("photo_url", ""),
            address=d.get("address", ""),
            open=d.get("open", ""),
            fee_yen=int(d.get("fee_yen", 0)),
            description=d.get("description", ""),
        )


def load_restaurants() -> List[Restaurant]:
    if not DATA_PATH.exists():
        st.error(f"データが見つかりません: {DATA_PATH}")
        return []
    raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return [Restaurant.from_dict(x) for x in raw]


def smoking_label(code: str) -> str:
    return {"no": "禁煙", "yes": "喫煙可", "separated": "分煙"}.get(code, code)


def yen(n: int) -> str:
    return f"¥{n:,}"


def init_state():
    st.session_state.setdefault("page", "search")  # search | results | detail | done
    st.session_state.setdefault("people", None)  # int
    st.session_state.setdefault("smoking", "either")  # no | yes | separated | either
    st.session_state.setdefault("arrival_min", 0)  # 0/15/30/60
    st.session_state.setdefault("selected_restaurant_id", None)
    st.session_state.setdefault("view_mode", "list")  # list | map
    st.session_state.setdefault("last_results", [])  # list[restaurant_id]
    st.session_state.setdefault("user_lat", DEFAULT_LAT)
    st.session_state.setdefault("user_lon", DEFAULT_LON)


def goto(page: str):
    st.session_state.page = page


# =========================
# UI helpers
# =========================
def inject_css():
    st.markdown(
        """
<style>
/* 全体の余白をスマホっぽく */
.block-container { padding-top: 1.2rem; padding-bottom: 2rem; max-width: 520px; }

/* “カード” */
.card {
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 18px;
  padding: 14px 14px;
  margin-bottom: 12px;
}

/* 主要ボタンの高さ */
.stButton > button {
  width: 100%;
  height: 48px;
  border-radius: 14px;
  font-weight: 700;
}

/* 小さめボタン */
.btn-sm .stButton > button { height: 40px; border-radius: 12px; font-weight: 700; }

/* セグメントっぽく見せる */
.seg {
  display:flex; gap:8px;
}
.seg .stButton{ flex:1; }

/* ラベル */
.label {
  font-size: 12px;
  color: rgba(229,231,235,0.75);
  margin-bottom: 6px;
}

/* チップ */
.chip {
  display:inline-block;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(59,130,246,0.16);
  border: 1px solid rgba(59,130,246,0.22);
  color: rgba(229,231,235,0.95);
  font-size: 12px;
  margin-right: 6px;
}
.meta {
  color: rgba(229,231,235,0.75);
  font-size: 12px;
}
.title {
  font-size: 18px;
  font-weight: 800;
  margin-bottom: 4px;
}
.hr { height:1px; background: rgba(255,255,255,0.06); margin: 10px 0; }
.small { font-size: 12px; color: rgba(229,231,235,0.70); }
</style>
        """,
        unsafe_allow_html=True,
    )


# =========================
# Pages
# =========================
def page_search(restaurants: List[Restaurant]):
    st.markdown(f"### 検索条件設定")
    st.caption("入社1年目でも迷わない。2次会を “一発で予約” まで。")

    # 人数
    st.markdown('<div class="label">人数</div>', unsafe_allow_html=True)
    people = st.selectbox(
        "人数を選択",
        options=[None, 1, 2, 3, 4, 5, 6, 7, 8],
        format_func=lambda x: "人数を選択" if x is None else f"{x}名",
        index=0 if st.session_state.people is None else [None,1,2,3,4,5,6,7,8].index(st.session_state.people),
        label_visibility="collapsed",
    )
    st.session_state.people = people

    # 喫煙
    st.markdown('<div class="label">喫煙設定</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("禁煙", use_container_width=True):
            st.session_state.smoking = "no"
    with c2:
        if st.button("喫煙", use_container_width=True):
            st.session_state.smoking = "yes"
    with c3:
        if st.button("どちらでも", use_container_width=True):
            st.session_state.smoking = "either"

    st.markdown(
        f'<div class="small">現在: <b>{ "禁煙" if st.session_state.smoking=="no" else "喫煙" if st.session_state.smoking=="yes" else "どちらでも" }</b></div>',
        unsafe_allow_html=True,
    )

    # 来店時間
    st.markdown('<div class="label">来店時間</div>', unsafe_allow_html=True)
    arrival_label = next(x[0] for x in ARRIVAL_OPTIONS if x[1] == st.session_state.arrival_min)
    chosen = st.selectbox(
        "来店時間を選択",
        options=[x[0] for x in ARRIVAL_OPTIONS],
        index=[x[0] for x in ARRIVAL_OPTIONS].index(arrival_label),
        label_visibility="collapsed",
    )
    st.session_state.arrival_min = dict(ARRIVAL_OPTIONS)[chosen]

    st.markdown("<div class='hr'></div>", unsafe_allow_html=True)

    # 検索ボタン
    if st.button("🔎 近くのお店を探す", use_container_width=True):
        if st.session_state.people is None:
            st.error("人数が未選択です。何名か選択してください。")
            return
        goto("results")


def filter_and_rank(restaurants: List[Restaurant]) -> pd.DataFrame:
    people = int(st.session_state.people)
    smoking = st.session_state.smoking
    user_lat = float(st.session_state.user_lat)
    user_lon = float(st.session_state.user_lon)

    rows = []
    for r in restaurants:
        if r.capacity < people:
            continue
        if smoking != "either":
            # 禁煙なら no のみ。喫煙なら yes/separated を許容…等、運用で調整
            if smoking == "no" and r.smoking != "no":
                continue
            if smoking == "yes" and r.smoking == "no":
                continue

        dist_km = haversine_km(user_lat, user_lon, r.lat, r.lon)
        # 超簡易スコア：近さ + 評価
        score = (r.rating * 2.0) - (dist_km * 1.2)
        rows.append(
            {
                "id": r.id,
                "name": r.name,
                "rating": r.rating,
                "price_yen": r.price_yen,
                "smoking": r.smoking,
                "capacity": r.capacity,
                "lat": r.lat,
                "lon": r.lon,
                "distance_km": dist_km,
                "fee_yen": r.fee_yen,
                "genre": "・".join(r.genre),
                "area": r.area,
                "score": score,
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.sort_values(["score", "rating"], ascending=False).reset_index(drop=True)
    return df


def results_header(df: pd.DataFrame):
    people = int(st.session_state.people)
    smoking = st.session_state.smoking
    arrival_min = int(st.session_state.arrival_min)

    chips = []
    chips.append(f"{people}名以上")
    chips.append("禁煙" if smoking == "no" else "喫煙" if smoking == "yes" else "喫煙どちらでも")
    chips.append("今すぐ" if arrival_min == 0 else f"{arrival_min}分後")

    st.markdown("### 検索結果")
    st.markdown("".join([f"<span class='chip'>{c}</span>" for c in chips]), unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        if st.button("📄 一覧", use_container_width=True):
            st.session_state.view_mode = "list"
    with c2:
        if st.button("🗺️ マップ", use_container_width=True):
            st.session_state.view_mode = "map"

    st.caption(f"{len(df)}件ヒット（デモデータ）")


def card_restaurant(row: pd.Series):
    dist_m = int(row["distance_km"] * 1000)
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown(f"<div class='title'>{row['name']}</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='meta'>⭐ {row['rating']:.1f}　・ {row['genre']}　・ 予算 {yen(int(row['price_yen']))}〜</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div class='meta'>🚶 約{dist_m}m　・ {smoking_label(row['smoking'])}　・ 最大{int(row['capacity'])}名</div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div class='hr'></div>", unsafe_allow_html=True)

    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button(f"👀 詳細を見る", key=f"detail_{row['id']}"):
            st.session_state.selected_restaurant_id = row["id"]
            goto("detail")
    with c2:
        if st.button(f"⚡ {int(st.session_state.people)}名で予約", key=f"quick_{row['id']}"):
            st.session_state.selected_restaurant_id = row["id"]
            goto("done")

    st.markdown("</div>", unsafe_allow_html=True)


def render_map(df: pd.DataFrame):
    if df.empty:
        st.info("条件に合うお店が見つかりません。条件を変えてください。")
        return

    view_state = pdk.ViewState(
        latitude=float(st.session_state.user_lat),
        longitude=float(st.session_state.user_lon),
        zoom=14,
        pitch=0,
    )

    map_df = df.copy()
    map_df["color_r"] = 59
    map_df["color_g"] = 130
    map_df["color_b"] = 246

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=map_df,
        get_position="[lon, lat]",
        get_radius=65,
        get_fill_color="[color_r, color_g, color_b]",
        pickable=True,
    )

    tooltip = {"text": "{name}\n⭐{rating}\n約{distance_km}km"}
    st.pydeck_chart(pdk.Deck(map_style=None, initial_view_state=view_state, layers=[layer], tooltip=tooltip))

    # マップ下にも一覧を軽く
    st.markdown("#### 上位候補（タップで詳細）")
    for _, row in df.head(5).iterrows():
        if st.button(f"{row['name']}（⭐{row['rating']:.1f} / 約{int(row['distance_km']*1000)}m）", key=f"pick_{row['id']}"):
            st.session_state.selected_restaurant_id = row["id"]
            goto("detail")


def page_results(restaurants: List[Restaurant]):
    df = filter_and_rank(restaurants)
    results_header(df)

    if st.button("← 条件を戻る"):
        goto("search")
        return

    if df.empty:
        st.info("条件に合うお店がありません。人数・喫煙条件を変えて再検索してください。")
        return

    st.session_state.last_results = df["id"].tolist()

    if st.session_state.view_mode == "map":
        render_map(df)
    else:
        for _, row in df.iterrows():
            card_restaurant(row)


def get_restaurant_by_id(restaurants: List[Restaurant], rid: str) -> Optional[Restaurant]:
    for r in restaurants:
        if r.id == rid:
            return r
    return None


def page_detail(restaurants: List[Restaurant]):
    rid = st.session_state.selected_restaurant_id
    r = get_restaurant_by_id(restaurants, rid) if rid else None
    if not r:
        st.error("店舗が見つかりません。")
        if st.button("検索結果へ戻る"):
            goto("results")
        return

    st.markdown("### 店舗詳細")
    st.caption("“2次会の正解” を、迷わず確保。")

    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown(f"<div class='title'>{r.name}</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='meta'>⭐ {r.rating:.1f}　・ {'・'.join(r.genre)}　・ 予算 {yen(r.price_yen)}〜</div>",
        unsafe_allow_html=True,
    )
    st.markdown(f"<div class='meta'>📍 {r.address}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='meta'>🕒 {r.open}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='meta'>🚬 {smoking_label(r.smoking)}　・ 最大{r.capacity}名</div>", unsafe_allow_html=True)
    st.markdown("<div class='hr'></div>", unsafe_allow_html=True)
    st.markdown(f"<div>{r.description}</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # 予約条件の要約
    people = int(st.session_state.people)
    arrival_min = int(st.session_state.arrival_min)
    when = "今すぐ" if arrival_min == 0 else f"{arrival_min}分後"

    st.markdown("#### 予約内容")
    st.markdown(
        f"<div class='card'><div class='meta'>👥 {people}名 / ⏱️ {when} / 💰 予算目安 {yen(r.price_yen)}〜</div></div>",
        unsafe_allow_html=True,
    )

    if st.button(f"⚡ この店を予約（{yen(r.fee_yen)}）" if r.fee_yen > 0 else "⚡ この店を予約", use_container_width=True):
        goto("done")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("← 検索結果へ", use_container_width=True):
            goto("results")
    with c2:
        if st.button("🏠 条件画面へ", use_container_width=True):
            goto("search")


def page_done(restaurants: List[Restaurant]):
    rid = st.session_state.selected_restaurant_id
    r = get_restaurant_by_id(restaurants, rid) if rid else None
    if not r:
        st.error("予約対象が見つかりません。")
        if st.button("検索へ戻る"):
            goto("search")
        return

    people = int(st.session_state.people)
    arrival_min = int(st.session_state.arrival_min)
    when = "今すぐ" if arrival_min == 0 else f"{arrival_min}分後"

    st.markdown("### ✅ 予約が完了しました！")
    st.caption("ここまで “一発”。あとは向かうだけ。")

    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<div class='title'>予約内容</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='meta'>🏷️ 店舗：{r.name}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='meta'>👥 人数：{people}名</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='meta'>⏱️ 来店：{when}</div>", unsafe_allow_html=True)
    if r.fee_yen > 0:
        st.markdown(f"<div class='meta'>💳 手数料：{yen(r.fee_yen)}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='meta'>📍 住所：{r.address}</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # 道順（Google MapsのURL生成。Streamlitからリンク表示）
    gmaps = f"https://www.google.com/maps/dir/?api=1&destination={r.lat},{r.lon}"
    st.link_button("🧭 お店への道順を表示", gmaps, use_container_width=True)

    if st.button("トップに戻る", use_container_width=True):
        # 予約後の状態は残してもいいが、ここでは初期化寄りに戻す
        st.session_state.selected_restaurant_id = None
        goto("search")


# =========================
# Main
# =========================
def main():
    st.set_page_config(page_title=APP_TITLE, page_icon="🍻", layout="centered")
    inject_css()
    init_state()

    restaurants = load_restaurants()

    # ヘッダー（アプリっぽく）
    st.markdown(f"## 🍻 {APP_TITLE}")

    if st.session_state.page == "search":
        page_search(restaurants)
    elif st.session_state.page == "results":
        page_results(restaurants)
    elif st.session_state.page == "detail":
        page_detail(restaurants)
    elif st.session_state.page == "done":
        page_done(restaurants)
    else:
        st.session_state.page = "search"
        page_search(restaurants)


if __name__ == "__main__":
    main()
