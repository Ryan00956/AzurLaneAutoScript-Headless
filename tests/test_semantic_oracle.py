import copy
import unittest

from alas_headless.semantic_oracle import (
    Bounds,
    BuildPool,
    CommissionStatus,
    DormState,
    MissionDisposition,
    OracleFingerprint,
    Point,
    SemanticGateClosed,
    SemanticOracle,
    SemanticTextTarget,
    SemanticToggleTarget,
    ResearchProjectStatus,
    TacticalSlotStatus,
)


DRIVER_REVISION = "be80ce591a481c12d60c50d6040d40c035b40a2b"
PACKAGE = "com.bilibili.azurlane"
COMPONENT = "com.bilibili.azurlane/com.manjuu.azurlane.MainActivity"


def make_button(name, path, x=640.0, y=360.0, bounds=None, raycast_top=True):
    if bounds is None:
        bounds = {"left": x - 20, "top": y - 20, "right": x + 20, "bottom": y + 20}
    return {
        "name": name,
        "path": path,
        "active_in_hierarchy": True,
        "active_and_enabled": True,
        "interactable": True,
        "raycast_top": raycast_top,
        "adb_point": {"x": x, "y": y},
        "adb_bounds": bounds,
    }


def make_snapshot(generation=10, age_ms=20):
    return {
        "protocol_schema": "alas-headless.observer/v1",
        "status": "ok",
        "package": PACKAGE,
        "pid": 1234,
        "peer_uid": 2000,
        "driver_revision": DRIVER_REVISION,
        "snapshot_schema": 1,
        "generation": generation,
        "age_ms": age_ms,
        "main_thread": True,
        "flags": 15,
        "ui_stage": 100,
        "ui_method_mask": 15,
        "width": 1280,
        "height": 720,
        "scene_handle": -76,
    }


def make_buttons(buttons, generation=10, age_ms=20):
    return {
        "protocol_schema": "alas-headless.observer/v1",
        "semantic_schema": "alas-headless.buttons/v1",
        "status": "ok",
        "package": PACKAGE,
        "pid": 1234,
        "peer_uid": 2000,
        "driver_revision": DRIVER_REVISION,
        "schema": 1,
        "generation": generation,
        "age_ms": age_ms,
        "button_count": len(buttons),
        "truncated": False,
        "error_count": 0,
        "buttons": buttons,
    }


def make_text(text, path="root/value", bounds=None, kind="ugui-text"):
    if bounds is None:
        bounds = {"left": 100.0, "top": 100.0, "right": 180.0, "bottom": 130.0}
    return {
        "kind": kind,
        "name": path.rsplit("/", 1)[-1],
        "path": path,
        "text": text,
        "flags": 271 if kind == "ugui-text" else 527,
        "active_in_hierarchy": True,
        "active_and_enabled": True,
        "adb_bounds": bounds,
    }


def make_image(path="root/icon", sprite="icon", bounds=None):
    if bounds is None:
        bounds = {"left": 200.0, "top": 100.0, "right": 240.0, "bottom": 140.0}
    return {
        "kind": "image",
        "name": path.rsplit("/", 1)[-1],
        "path": path,
        "sprite": sprite,
        "flags": 495,
        "active_in_hierarchy": True,
        "active_and_enabled": True,
        "raycast_target": False,
        "raycast_top": None,
        "color": {"red": 1.0, "green": 0.5, "blue": 0.25, "alpha": 1.0},
        "fill_amount": 1.0,
        "adb_bounds": bounds,
    }


def make_toggle(
    path="root/toggle",
    checked=False,
    raycast_top=True,
    x=640.0,
    y=360.0,
    bounds=None,
):
    value = make_button(
        path.rsplit("/", 1)[-1],
        path,
        x=x,
        y=y,
        bounds=bounds,
        raycast_top=raycast_top,
    )
    value.update({"kind": "toggle", "flags": 0x1D07, "checked": checked})
    return value


def make_ui(texts, toggles=None, images=None, generation=10, age_ms=20):
    toggles = [] if toggles is None else toggles
    images = [] if images is None else images
    return {
        "protocol_schema": "alas-headless.observer/v1",
        "semantic_schema": "alas-headless.ui/v1",
        "status": "ok",
        "package": PACKAGE,
        "pid": 1234,
        "peer_uid": 2000,
        "driver_revision": DRIVER_REVISION,
        "schema": 1,
        "generation": generation,
        "age_ms": age_ms,
        "method_mask": 15,
        "toggle_count": len(toggles),
        "text_count": len(texts),
        "image_count": len(images),
        "toggle_truncated": False,
        "text_truncated": False,
        "image_truncated": False,
        "error_count": 0,
        "skipped_count": 0,
        "toggles": toggles,
        "texts": texts,
        "images": images,
    }


def set_commission_scroll_view(
    backend,
    *,
    index,
    name,
    handle_top,
    generation,
    handle_raycast_top=True,
    duration="01:00:00",
):
    page = "root/UICamera/Canvas/UIMain/EventUI(Clone)"
    row = page + "/scrollRect$/content/{0}".format(index)
    backend.snapshot = make_snapshot(generation=generation)
    backend.buttons = make_buttons(
        [
            make_button("back_btn", page + "/blur_panel/adapt/top/back_btn"),
            make_button("bgNormal$", row + "/bgNormal$", 640, 190),
        ],
        generation=generation,
    )
    track = make_image(
        page + "/blur_panel/adapt/scroll_bar",
        "white_dot",
        {"left": 1255, "top": 75, "right": 1259, "bottom": 675},
    )
    handle = make_image(
        page + "/blur_panel/adapt/scroll_bar/Image",
        "scroll_bar",
        {
            "left": 1250,
            "top": handle_top,
            "right": 1264,
            "bottom": handle_top + 480,
        },
    )
    handle["raycast_target"] = True
    handle["raycast_top"] = handle_raycast_top
    backend.ui = make_ui(
        [
            make_text(name, row + "/labelName$"),
            make_text("15", row + "/level/labelLv$"),
            make_text(duration, row + "/labelTime$/Text"),
        ],
        images=[
            make_image(row + "/iconState$/0", "kongxian_bg"),
            make_image(row + "/iconType$", "faxiankuangmai"),
            track,
            handle,
        ],
        generation=generation,
    )


class FakeBackend:
    def __init__(self, buttons):
        self.snapshot = make_snapshot()
        self.buttons = make_buttons(buttons)
        self.buttons_sequence = []
        self.ui = make_ui([])
        self.ui_sequence = []
        self.foreground = COMPONENT
        self.taps = []
        self.swipes = []
        self.on_tap = None
        self.on_swipe = None

    def request(self, request_line):
        if request_line == "GET /v1/snapshot\n":
            return copy.deepcopy(self.snapshot)
        if request_line == "GET /v1/buttons\n":
            if self.buttons_sequence:
                return copy.deepcopy(self.buttons_sequence.pop(0))
            return copy.deepcopy(self.buttons)
        if request_line == "GET /v1/ui\n":
            if self.ui_sequence:
                return copy.deepcopy(self.ui_sequence.pop(0))
            return copy.deepcopy(self.ui)
        raise AssertionError("unexpected request")

    def foreground_component(self):
        return self.foreground

    def tap(self, x, y):
        self.taps.append((x, y))
        if self.on_tap is not None:
            self.on_tap()

    def swipe(self, x1, y1, x2, y2, duration_ms):
        self.swipes.append((x1, y1, x2, y2, duration_ms))
        if self.on_swipe is not None:
            self.on_swipe()


def make_oracle(backend):
    return SemanticOracle(
        backend.request,
        backend.foreground_component,
        backend.tap,
        OracleFingerprint(
            package=PACKAGE,
            component=COMPONENT,
            driver_revision=DRIVER_REVISION,
            expected_pid=1234,
        ),
        sleep=lambda _: None,
        swipe=backend.swipe,
    )


class SemanticOracleTests(unittest.TestCase):
    def test_exact_text_marker_and_indexed_list_groups(self):
        backend = FakeBackend([])
        backend.ui = make_ui(
            [
                make_text("空空如也", "root/page/empty", {"left": 10, "top": 10, "right": 90, "bottom": 30}),
                make_text("委托甲", "root/list/1/name", {"left": 20, "top": 120, "right": 100, "bottom": 140}),
                make_text("01:30:00", "root/list/1/time", {"left": 120, "top": 120, "right": 200, "bottom": 140}),
                make_text("委托零", "root/list/0/name", {"left": 20, "top": 60, "right": 100, "bottom": 80}),
            ]
        )
        oracle = SemanticOracle(
            backend.request,
            backend.foreground_component,
            backend.tap,
            OracleFingerprint(
                package=PACKAGE,
                component=COMPONENT,
                driver_revision=DRIVER_REVISION,
                expected_pid=1234,
            ),
            text_targets=(
                SemanticTextTarget("page/empty", "root/page/empty", ("空空如也",)),
            ),
            sleep=lambda _: None,
        )

        self.assertEqual(oracle.text_state("page/empty").text, "空空如也")
        groups = oracle.indexed_text_groups("root/list")
        self.assertEqual([group.index for group in groups], [0, 1])
        self.assertEqual([item.text for item in groups[1].texts], ["委托甲", "01:30:00"])

    def test_typed_countdown_parser_is_strict(self):
        self.assertEqual(SemanticOracle.parse_countdown_seconds("09:42"), 582)
        self.assertEqual(
            SemanticOracle.parse_countdown_seconds("12:34:56"), 45296
        )
        for value in ("9:42", "01:60", "完成", "1d 02:03:04"):
            with self.subTest(value=value):
                with self.assertRaises(SemanticGateClosed):
                    SemanticOracle.parse_countdown_seconds(value)

    def test_typed_toggle_state_and_click_require_top_raycast(self):
        path = "root/options/merit"
        backend = FakeBackend([])
        backend.ui = make_ui([], toggles=[make_toggle(path, checked=True)])
        oracle = SemanticOracle(
            backend.request,
            backend.foreground_component,
            backend.tap,
            OracleFingerprint(
                package=PACKAGE,
                component=COMPONENT,
                driver_revision=DRIVER_REVISION,
                expected_pid=1234,
            ),
            toggle_targets=(SemanticToggleTarget("mail/filter/merit", "merit", path),),
            sleep=lambda _: None,
        )

        self.assertTrue(oracle.toggle_selected("mail/filter/merit"))
        receipt = oracle.click_toggle("mail/filter/merit")
        self.assertEqual(receipt.path, path)
        self.assertEqual(backend.taps, [(640, 360)])

        backend.ui = make_ui(
            [], toggles=[make_toggle(path, checked=True, raycast_top=False)]
        )
        with self.assertRaises(SemanticGateClosed):
            oracle.click_toggle("mail/filter/merit")
        self.assertEqual(backend.taps, [(640, 360)])

    def test_duplicate_mail_toggle_paths_are_disambiguated_by_child_sprite(self):
        path = (
            "root/MailMgrMsgboxUI(Clone)/window/frame/toggle_group/filter/"
            "content/toggle_tpl(Clone)"
        )
        gold_bounds = {"left": 558, "top": 390, "right": 639, "bottom": 431}
        oil_bounds = {"left": 678, "top": 390, "right": 759, "bottom": 431}
        backend = FakeBackend([])
        backend.ui = make_ui(
            [],
            toggles=[
                make_toggle(path, x=598, y=410, bounds=gold_bounds),
                make_toggle(path, x=718, y=410, bounds=oil_bounds),
            ],
            images=[
                make_image(
                    path + "/Image",
                    "gold",
                    {"left": 599, "top": 394, "right": 632, "bottom": 427},
                ),
                make_image(
                    path + "/Image",
                    "oil",
                    {"left": 719, "top": 394, "right": 752, "bottom": 427},
                ),
            ],
        )
        oracle = make_oracle(backend)

        receipt = oracle.click_toggle("mail/manage/oil")

        self.assertEqual(receipt.point, Point(718, 410))
        self.assertEqual(backend.taps, [(718, 410)])

    def test_mail_empty_uses_explicit_typed_counter(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_btn",
                    "root/MailUI(Clone)/adapt/CommonTitleAndBack/back_btn",
                    51,
                    49,
                )
            ]
        )
        counter_path = (
            "root/MailUI(Clone)/adapt/main/content/left/left_content/top/count"
        )
        backend.ui = make_ui(
            [make_text("<color=#fff>0</color>/<color=#222>100</color>", counter_path)]
        )
        oracle = make_oracle(backend)

        self.assertEqual(oracle.mail_count(), (0, 100))
        self.assertTrue(oracle.mail_is_empty())

        backend.ui = make_ui([make_text("59/100", counter_path)])
        self.assertFalse(oracle.mail_is_empty())

    def test_mission_empty_requires_explicit_typed_marker(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_btn",
                    "root/TaskScene(Clone)/blur_panel/adapt/top/back_btn",
                    58,
                    53,
                )
            ]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "没有进行中的任务",
                    "root/TaskScene(Clone)/TaskEmptyListUI(Clone)/Text",
                    {"left": 156, "top": 278, "right": 1280, "bottom": 441},
                )
            ]
        )

        state = make_oracle(backend).mission_page_state()

        self.assertEqual(state.disposition, MissionDisposition.EMPTY)

    def test_main_badges_use_exact_typed_markers(self):
        backend = FakeBackend(
            [
                make_button(
                    "mail", "root/NewMainMellowTheme(Clone)/frame/top/btns/mail"
                ),
                make_button(
                    "task", "root/NewMainMellowTheme(Clone)/frame/bottom/frame/task"
                ),
                make_button(
                    "live", "root/NewMainMellowTheme(Clone)/frame/bottom/frame/live"
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "3",
                    "root/NewMainMellowTheme(Clone)/frame/top/btns/mail/Text",
                )
            ]
        )
        backend.ui["images"].append(
            make_image(
                "root/NewMainMellowTheme(Clone)/frame/bottom/frame/live/tip",
                "reddot",
            )
        )
        backend.ui["image_count"] += 1
        oracle = make_oracle(backend)

        self.assertEqual(oracle.main_mail_unread_count(), 3)
        self.assertFalse(oracle.main_red_dot("main/task"))
        self.assertTrue(oracle.main_red_dot("main/live"))

    def test_build_pool_and_costs_use_exact_typed_controls(self):
        base = (
            "root/UICamera/Canvas/UIMain/BuildShipUI(Clone)/"
            "BuildShipPoolsPageUI(Clone)/gallery/"
        )
        backend = FakeBackend(
            [make_button("start_btn", base + "start_btn", 1127, 636)]
        )
        toggles = [
            make_toggle(
                base + "toggle_bg/bg/toggles/" + name + "/frame",
                checked=name == "heavy",
            )
            for name in ("light", "heavy", "special")
        ]
        backend.ui = make_ui(
            [
                make_text("3661", base + "res_items/item/Text"),
                make_text("2", base + "item_bg/item/Text"),
                make_text("1500", base + "item_bg/gold/Text"),
            ],
            toggles=toggles,
        )
        oracle = make_oracle(backend)

        self.assertEqual(oracle.build_selected_pool(), BuildPool.HEAVY)
        costs = oracle.build_costs()
        self.assertEqual(costs.cubes_owned, 3661)
        self.assertEqual(costs.cubes_per_build, 2)
        self.assertEqual(costs.coins_per_build, 1500)

    def test_build_pool_requires_exactly_one_selected_toggle(self):
        base = (
            "root/UICamera/Canvas/UIMain/BuildShipUI(Clone)/"
            "BuildShipPoolsPageUI(Clone)/gallery/"
        )
        backend = FakeBackend([make_button("start_btn", base + "start_btn")])
        backend.ui = make_ui(
            [],
            toggles=[
                make_toggle(
                    base + "toggle_bg/bg/toggles/" + name + "/frame",
                    checked=False,
                )
                for name in ("light", "heavy", "special")
            ],
        )

        with self.assertRaises(SemanticGateClosed):
            make_oracle(backend).build_selected_pool()

    def test_build_queue_uses_selected_tab_capacity_and_exact_two_slot_timers(self):
        page = "root/Overlay/UIMain/blur_panel/"
        queue = (
            "root/UICamera/Canvas/UIMain/BuildShipUI(Clone)/"
            "BuildShipDetailUI1(Clone)/"
        )
        backend = FakeBackend(
            [make_button("back_btn", page + "adapt/top/back_btn", 58, 53)]
        )
        backend.ui = make_ui(
            [
                make_text("2", queue + "title/value"),
                make_text(
                    "99:99:99",
                    queue
                    + "list_single_line/content/project_1/frame/buiding/timer/Text",
                ),
                make_text(
                    "01:29:41",
                    queue
                    + "list_single_line/content/project_2/frame/buiding/timer/Text",
                ),
            ],
            toggles=[
                make_toggle(
                    page
                    + "adapt/left_length/frame/tagRoot/queue_btn",
                    checked=True,
                )
            ],
        )
        oracle = make_oracle(backend)

        self.assertEqual(oracle.build_queue_timers(), ("99:99:99", "01:29:41"))
        self.assertFalse(oracle.build_queue_empty())

        backend.ui["texts"][2]["text"] = "99:99:99"
        self.assertTrue(oracle.build_queue_empty())

        backend.ui["texts"][2]["text"] = "not-a-timer"
        with self.assertRaises(SemanticGateClosed):
            oracle.build_queue_timers()

    def test_campaign_menu_and_chapter_page_are_distinct_typed_states(self):
        root = "root/UICamera/Canvas/UIMain/LevelMainScene(Clone)/"
        back = make_button(
            "back_button", root + "top/top_chapter/back_button", 58, 54
        )
        menu_backend = FakeBackend(
            [
                back,
                make_button(
                    "enter_main", root + "entrance/enters/enter_main", 339, 336
                ),
            ]
        )
        self.assertTrue(make_oracle(menu_backend).campaign_menu_is_entry())

        stage_buttons = [
            make_button(
                "Chapter_1201",
                root + "float/levels/items/Chapter_1201",
                187,
                355,
                raycast_top=None,
            ),
            make_button(
                "Chapter_1202",
                root + "float/levels/items/Chapter_1202",
                367,
                602,
                raycast_top=None,
            ),
        ]
        chapter_backend = FakeBackend([back, *stage_buttons])
        texts = [
            make_text("马里亚纳风云上", root + "top/top_chapter/title_chapter/name")
        ]
        for stage_id, code, title in (
            (1201, "12–1  ", "先声夺人"),
            (1202, "12–2  ", "鲁莽的后果"),
        ):
            base = (
                root
                + "float/levels/items/Chapter_"
                + str(stage_id)
                + "/main/info/bk/title_form/"
            )
            texts.extend(
                [
                    make_text(code, base + "title_index"),
                    make_text(title, base + "title"),
                ]
            )
        chapter_backend.ui = make_ui(texts)
        oracle = make_oracle(chapter_backend)

        self.assertFalse(oracle.campaign_menu_is_entry())
        state = oracle.campaign_page_state()
        self.assertEqual(state.chapter_name, "马里亚纳风云上")
        self.assertEqual(
            [(item.stage_code, item.title) for item in state.stages],
            [("12-1", "先声夺人"), ("12-2", "鲁莽的后果")],
        )
        self.assertTrue(oracle.campaign_page_is_normal())

    def test_campaign_page_rejects_stage_id_text_mismatch(self):
        root = "root/UICamera/Canvas/UIMain/LevelMainScene(Clone)/"
        stage = root + "float/levels/items/Chapter_1201"
        backend = FakeBackend(
            [
                make_button("back_button", root + "top/top_chapter/back_button"),
                make_button("Chapter_1201", stage, raycast_top=None),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("第一章", root + "top/top_chapter/title_chapter/name"),
                make_text("12-2", stage + "/main/info/bk/title_form/title_index"),
                make_text("错误关卡", stage + "/main/info/bk/title_form/title"),
            ]
        )

        with self.assertRaises(SemanticGateClosed):
            make_oracle(backend).campaign_page_state()

    def test_dorm_state_uses_exact_typed_summary(self):
        page = "root/UICamera/Canvas/UIMain/CourtYardUI(Clone)/main/"
        backend = FakeBackend(
            [
                make_button(
                    "decorate_btn",
                    page + "bottomPanel/bottomright/decorate_btn",
                    977,
                    640,
                )
            ]
        )
        backend.ui = make_ui(
            [
                make_text("6/6", page + "bottomPanel/bottomleft/train_btn/Text"),
                make_text("0/40000", page + "bottomPanel/bottomleft/feed_btn/Text"),
                make_text("454", page + "topPanel/btns/topright/comfortable/Text"),
                make_text("1F", page + "topPanel/btns/topright/switch/Text"),
                make_text("", page + "bottomPanel/bottomleft/feed_btn/time"),
            ]
        )

        state = make_oracle(backend).dorm_state()

        self.assertEqual(
            state,
            DormState(
                occupied_slots=6,
                total_slots=6,
                food=0,
                food_capacity=40000,
                comfort=454,
                floor=1,
                food_countdown_seconds=None,
            ),
        )

    def test_dorm_state_rejects_inconsistent_capacity(self):
        page = "root/UICamera/Canvas/UIMain/CourtYardUI(Clone)/main/"
        backend = FakeBackend(
            [make_button("decorate_btn", page + "bottomPanel/bottomright/decorate_btn")]
        )
        backend.ui = make_ui(
            [
                make_text("7/6", page + "bottomPanel/bottomleft/train_btn/Text"),
                make_text("1/40000", page + "bottomPanel/bottomleft/feed_btn/Text"),
                make_text("454", page + "topPanel/btns/topright/comfortable/Text"),
                make_text("1F", page + "topPanel/btns/topright/switch/Text"),
                make_text("01:02:03", page + "bottomPanel/bottomleft/feed_btn/time"),
            ]
        )

        with self.assertRaises(SemanticGateClosed):
            make_oracle(backend).dorm_state()

    def test_dorm_statistics_blocks_page_but_allows_exact_confirm(self):
        page = "root/UICamera/Canvas/UIMain/CourtYardUI(Clone)/main/"
        backend = FakeBackend(
            [
                make_button(
                    "decorate_btn",
                    page + "bottomPanel/bottomright/decorate_btn",
                ),
                make_button(
                    "confirm_btn",
                    "root/Overlay/UIMain/BackYardStatisticsUI(Clone)/"
                    "painting/confirm_btn",
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertFalse(oracle.enabled("dorm/page/manage"))
        self.assertTrue(oracle.enabled("dorm/statistics/confirm"))

    def test_dorm_feed_uses_food_card_image_not_purchase_plus(self):
        dorm = "root/UICamera/Canvas/UIMain/CourtYardUI(Clone)/main/"
        feed = "root/UICamera/Canvas/UIMain/BackYardFeedUI(Clone)/"
        backend = FakeBackend(
            [
                make_button(
                    "decorate_btn",
                    dorm + "bottomPanel/bottomright/decorate_btn",
                ),
                make_button("close", feed + "close", 320, 540),
            ]
        )
        texts = [make_text("0/40000", feed + "frame/Text")]
        images = []
        for offset, item_id in enumerate(range(50001, 50007)):
            root = feed + "frame/food_{0}/".format(item_id)
            texts.extend(
                [
                    make_text("食物{0}".format((1, 2, 3, 5, 10, 20)[offset] * 1000), root + "Text"),
                    make_text(str(10 - offset), root + "icon_bg/count"),
                ]
            )
            image = make_image(
                root + "icon_bg",
                "bg2",
                {
                    "left": 395 + offset * 128,
                    "top": 375,
                    "right": 499 + offset * 128,
                    "bottom": 480,
                },
            )
            image["raycast_target"] = True
            image["raycast_top"] = True
            images.append(image)
        backend.ui = make_ui(texts, images=images)
        oracle = make_oracle(backend)

        state = oracle.dorm_feed_state()
        receipt = oracle.click_dorm_food(50001)

        self.assertEqual(state.items[0].count, 10)
        self.assertEqual(state.items[0].button.name, "icon_bg")
        self.assertTrue(receipt.path.endswith("food_50001/icon_bg"))
        self.assertEqual(backend.taps, [(447, 428)])

    def test_build_submit_dialog_cross_checks_count_and_typed_costs(self):
        base = (
            "root/UICamera/Canvas/UIMain/BuildShipUI(Clone)/"
            "BuildShipPoolsPageUI(Clone)/gallery/"
        )
        prep = "root/Overlay/UIMain/BuildShipMsgBoxUI(Clone)/window/"
        backend = FakeBackend(
            [
                make_button("start_btn", base + "start_btn"),
                make_button("confirm_btn", prep + "btns/confirm_btn"),
                make_button("cancel_btn", prep + "btns/cancel_btn"),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("3662", base + "res_items/item/Text"),
                make_text("2", base + "item_bg/item/Text"),
                make_text("1500", base + "item_bg/gold/Text"),
                make_text("1", prep + "content/calc_panel/Text"),
                make_text(
                    "建造「1艘」舰船需要消耗: 「1500物资」和「2个心智魔方」",
                    prep + "content/Text",
                ),
            ],
            toggles=[
                make_toggle(
                    base + "toggle_bg/bg/toggles/" + name + "/frame",
                    checked=name == "heavy",
                )
                for name in ("light", "heavy", "special")
            ],
        )

        state = make_oracle(backend).build_submit_state()

        self.assertEqual(state.count, 1)
        self.assertEqual(state.cubes_owned, 3662)
        self.assertEqual(state.cubes_required, 2)
        self.assertEqual(state.coins_required, 1500)

    def test_research_start_confirm_requires_exact_resource_prompt(self):
        popup = "root/Overlay/UIMain/Msgbox(Clone)/window/"
        backend = FakeBackend(
            [
                make_button(
                    "custom_button_2(Clone)",
                    popup + "button_container/custom_button_2(Clone)",
                ),
                make_button(
                    "custom_button_1(Clone)",
                    popup + "button_container/custom_button_1(Clone)",
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "开启该科研项目需要消耗 :物资x1500",
                    popup + "msg_panel/content",
                ),
                make_text("取消", popup + "button_container/custom_button_2(Clone)/pic"),
                make_text("确定", popup + "button_container/custom_button_1(Clone)/pic"),
            ]
        )
        oracle = make_oracle(backend)

        self.assertEqual(oracle.research_start_prompt_cost(), ("gold", 1500))
        receipt = oracle.click("research/start/confirm")
        self.assertEqual(receipt.semantic_id, "research/start/confirm")

        backend.ui["texts"][0]["text"] = "开启该科研项目需要消耗 :钻石x1500"
        self.assertIsNone(oracle.research_start_prompt_cost())
        with self.assertRaises(SemanticGateClosed):
            oracle.click("research/start/confirm")

    def test_research_projects_follow_visual_slots_and_typed_status(self):
        page = "root/UICamera/Canvas/UIMain/TechnologyUI(Clone)"
        content = page + "/main/base_page/srcoll_rect/content/"
        visual = ((2, 180), (1, 410), (5, 640), (4, 870), (3, 1100))
        buttons = [
            make_button("back", page + "/blur_panel/adapt/top/back", 58, 54)
        ]
        texts = []
        images = []
        for slot, (unity_index, x) in enumerate(visual, start=1):
            root = content + str(unity_index)
            buttons.append(
                make_button(
                    str(unity_index),
                    root,
                    x,
                    360,
                    {"left": x - 80, "top": 100, "right": x + 80, "bottom": 610},
                )
            )
            frame = root + "/frame/"
            texts.extend(
                [
                    make_text("H-{0:03d}-MI".format(slot), frame + "name_bg/Text"),
                    make_text("小型项目", frame + "sub_name"),
                    make_text(
                        "<color=#776AB0FF>{0}</color>".format(
                            "进行中" if slot == 3 else "查看详情"
                        ),
                        frame + "marks/Text",
                    ),
                    make_text(
                        "00:24:43" if slot == 3 else "01:00:00",
                        frame + "marks/time",
                    ),
                ]
            )
            images.append(make_image(frame + "top/label/version", "version_9"))
        backend = FakeBackend(buttons)
        backend.ui = make_ui(texts, images=images)

        projects = make_oracle(backend).research_projects()

        self.assertEqual([item.unity_index for item in projects], [2, 1, 5, 4, 3])
        self.assertEqual([item.slot for item in projects], [1, 2, 3, 4, 5])
        self.assertEqual(projects[2].status, ResearchProjectStatus.RUNNING)
        self.assertEqual(projects[2].duration_seconds, 24 * 60 + 43)
        self.assertTrue(all(item.series == 9 for item in projects))

    def test_research_detail_and_queue_expose_typed_alas_inputs(self):
        selected = (
            "root/UICamera/Canvas/UIMain/TechnologyUI(Clone)/"
            "main/base_page/selecte_panel/"
        )
        card = selected + "technology_card/frame/"
        backend = FakeBackend(
            [
                make_button("selecte_panel", selected.rstrip("/")),
                make_button("start_btn", card + "btns/start_btn"),
                make_button("queue_btn", card + "btns/queue_btn"),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("G-412", card + "name_bg/Text"),
                make_text("基础研究", card + "sub_name"),
                make_text("01:00:00", selected + "timer/bg/Text"),
                make_text(
                    "10000/1500",
                    selected
                    + "consume_panel/bg/container/item_tpl/icon_bg/count",
                ),
                make_text(
                    "完成3次军事委托",
                    selected + "consume_panel/bg/task_panel/slider/Text",
                ),
            ],
            images=[
                make_image(
                    selected
                    + "consume_panel/bg/container/item_tpl/icon_bg/icon",
                    "gold",
                )
            ],
        )
        oracle = make_oracle(backend)

        detail = oracle.research_detail_state()

        self.assertEqual(detail.code, "G-412")
        self.assertEqual(detail.resource_id, "gold")
        self.assertEqual(detail.resource_required, 1500)
        self.assertTrue(detail.can_start)
        self.assertTrue(detail.can_queue)

        page = "root/UICamera/Canvas/UIMain/TechnologyUI(Clone)/"
        queue = page + "main/queue_page/queue_rect/content/1/frame/"
        backend.buttons = make_buttons(
            [
                make_button("back", page + "blur_panel/adapt/top/back"),
                make_button(
                    "btn_award",
                    page + "blur_panel/adapt/right/btn_award",
                    x=1279,
                    y=600,
                    bounds={
                        "left": 1190,
                        "top": 500,
                        "right": 1280,
                        "bottom": 650,
                    },
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("D-319", queue + "name_bg/Text"),
                make_text("研究完成", queue + "marks/Text"),
                make_text("00:00:00", queue + "marks/time"),
            ],
            images=[
                make_image(page + "blur_panel/adapt/top/title_queue", "title_queue"),
                make_image(queue + "top/label/version", "version_6"),
            ],
        )

        queue_state = oracle.research_queue_state()

        self.assertTrue(queue_state.reward_claimable)
        self.assertEqual(queue_state.empty_slots, 4)
        self.assertEqual(queue_state.entries[0].code, "D-319")
        self.assertEqual(
            queue_state.entries[0].status,
            ResearchProjectStatus.FINISHED,
        )

    def test_tactical_slots_use_typed_progress_and_countdown(self):
        page = "root/UICamera/Canvas/UIMain/NewNavalTacticsUI(Clone)/adpter/"
        students = page + "NewNavalTacticsStudentsPage(Clone)/"
        buttons = [make_button("btnBack", page + "frame/btnBack", 58, 54)]
        texts = []
        for index, (root_name, ship_id, x, timer) in enumerate(
            (
                ("info", "206054", 500, "01:02:03"),
                ("info(Clone)", "204044", 720, ""),
            )
        ):
            root = students + root_name
            bounds = {"left": x - 99, "top": 86, "right": x + 99, "bottom": 364}
            buttons.extend(
                [
                    make_button(ship_id, root + "/" + ship_id, x, 225, bounds),
                    make_button("cancel_btn", root + "/cancel_btn", x, 650),
                ]
            )
            text_bounds = {
                "left": x - 40,
                "top": 100,
                "right": x + 40,
                "bottom": 130,
            }
            texts.extend(
                [
                    make_text("舰船" + str(index), root + "/" + ship_id + "/content/info/name_mask/name", text_bounds),
                    make_text("117", root + "/" + ship_id + "/content/dockyard/lv/Text", text_bounds),
                    make_text("技能" + str(index), root + "/skill/name_Text", text_bounds),
                    make_text("9", root + "/skill/level", text_bounds),
                    make_text("2300/5800", root + "/skill/next", text_bounds),
                    make_text(timer, root + "/timer_Text", text_bounds),
                ]
            )
        backend = FakeBackend(buttons)
        backend.ui = make_ui(texts)

        slots = make_oracle(backend).tactical_slots()

        self.assertEqual([slot.ship_id for slot in slots], [206054, 204044])
        self.assertEqual(slots[0].status, TacticalSlotStatus.RUNNING)
        self.assertEqual(slots[0].remaining_seconds, 3723)
        self.assertEqual(slots[1].status, TacticalSlotStatus.FINISHED)
        self.assertIsNone(slots[1].remaining_seconds)

    def test_tactical_skill_and_book_inputs_use_typed_rows(self):
        skill_page = "root/Overlay/UIMain/NewNavalTacticsSkillsPage(Clone)/frame/"
        skill_row = skill_page + "skill_container/content/skill"
        backend = FakeBackend(
            [make_button("confirm_btn", skill_page + "confirm_btn")]
        )
        row_bounds = {"left": 100, "top": 80, "right": 900, "bottom": 260}
        row = make_image(skill_row, "skill", row_bounds)
        row["raycast_target"] = True
        row["raycast_top"] = True
        backend.ui = make_ui(
            [
                make_text("荆棘与坚盾", skill_row + "/name/Text/subText"),
                make_text("Lv.9", skill_row + "/name/level"),
                make_text("8400/10000", skill_row + "/next"),
            ],
            images=[row],
        )
        oracle = make_oracle(backend)

        skills = oracle.tactical_skills()
        skill_receipt = oracle.click_tactical_skill(0)

        self.assertEqual(skills[0].name, "荆棘与坚盾")
        self.assertFalse(skills[0].max_level)
        self.assertEqual(skill_receipt.semantic_id, "tactical/skill/0")

        lesson = "root/Overlay/UIMain/NewNavalTacticsLessonPage(Clone)/"
        item_path = lesson + "items/scorll/content/item"
        backend.buttons = make_buttons(
            [
                make_button("confirm_btn", lesson + "confirm_btn"),
                make_button("cancel_btn", lesson + "cancel_btn"),
            ]
        )
        item_bounds = {"left": 300, "top": 180, "right": 500, "bottom": 450}
        item = make_image(item_path, "item", item_bounds)
        item["raycast_target"] = True
        item["raycast_top"] = True
        backend.ui = make_ui(
            [
                make_text(
                    "3",
                    item_path + "/icon_bg/count",
                    {"left": 320, "top": 210, "right": 360, "bottom": 240},
                ),
                make_text(
                    "EXP200%",
                    item_path + "/addition",
                    {"left": 350, "top": 400, "right": 460, "bottom": 430},
                ),
            ],
            images=[
                item,
                make_image(
                    item_path + "/icon_bg/icon",
                    "16024",
                    {"left": 330, "top": 240, "right": 430, "bottom": 340},
                ),
                make_image(
                    item_path + "/selected",
                    "selected",
                    {"left": 310, "top": 190, "right": 490, "bottom": 440},
                ),
            ],
        )

        books = oracle.tactical_books()
        book_receipt = oracle.click_tactical_book(0)

        self.assertEqual(books[0].item_id, "16024")
        self.assertEqual((books[0].genre, books[0].tier), (3, 4))
        self.assertTrue(books[0].exp_bonus)
        self.assertEqual(book_receipt.semantic_id, "tactical/book/0")

    def test_tactical_continue_cancel_requires_exact_prompt_text(self):
        popup = "root/Overlay/UIMain/Msgbox(Clone)/window/"
        backend = FakeBackend(
            [
                make_button(
                    "custom_button_2(Clone)",
                    popup + "button_container/custom_button_2(Clone)",
                )
            ]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "<color=#92fc63>「追赶者」</color>学习完成，"
                    "<color=#92fc63>「816中队」</color>技能获得"
                    "<color=#92fc63>450</color>点经验是否继续学习该技能？",
                    popup + "msg_panel/content",
                ),
                make_text("取 消", popup + "button_container/custom_button_2(Clone)/pic"),
                make_text("确 定", popup + "button_container/custom_button_1(Clone)/pic"),
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.enabled("tactical/continue/cancel"))
        oracle.click("tactical/continue/cancel")
        self.assertEqual(backend.taps, [(640, 360)])

        backend.ui["texts"][0]["text"] = "是否购买资源？"
        self.assertFalse(oracle.enabled("tactical/continue/cancel"))

    def test_network_reconnect_confirm_requires_exact_networkdown_prompt(self):
        popup = "root/Overlay/UIMain/Msgbox(Clone)/window/"
        backend = FakeBackend(
            [
                make_button(
                    "custom_button_2(Clone)",
                    popup + "button_container/custom_button_2(Clone)",
                ),
                make_button(
                    "custom_button_1(Clone)",
                    popup + "button_container/custom_button_1(Clone)",
                ),
                make_button(
                    "back_btn",
                    "root/UICamera/Canvas/UIMain/EventUI(Clone)/blur_panel/"
                    "adapt/top/back_btn",
                    raycast_top=False,
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "服务器连接失败，是否重新连接？\n[NetworkDown]",
                    popup + "msg_panel/content",
                ),
                make_text(
                    "取 消",
                    popup + "button_container/custom_button_2(Clone)/pic",
                ),
                make_text(
                    "确 定",
                    popup + "button_container/custom_button_1(Clone)/pic",
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.enabled("overlay/network-reconnect/cancel"))
        self.assertTrue(oracle.enabled("overlay/network-reconnect/confirm"))
        receipt = oracle.click("overlay/network-reconnect/confirm")
        self.assertEqual(receipt.semantic_id, "overlay/network-reconnect/confirm")
        self.assertEqual(backend.taps, [(640, 360)])

        backend.ui["texts"][0]["text"] = "是否购买资源？"
        self.assertFalse(oracle.enabled("overlay/network-reconnect/confirm"))

    def test_reward_summary_counter_requires_exact_typed_page_identity(self):
        backend = FakeBackend(
            [
                make_button(
                    "CommissionInfoUI4Mellow(Clone)",
                    "root/Overlay/UIMain/CommissionInfoUI4Mellow(Clone)",
                    827,
                    622,
                    {"left": 0, "top": 0, "right": 1280, "bottom": 720},
                )
            ]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "3",
                    "root/CommissionInfoUI4Mellow(Clone)/frame/main/content/"
                    "event/frame/counter/finished/Text",
                )
            ]
        )

        self.assertEqual(
            make_oracle(backend).reward_summary_count("commission", "finished"),
            3,
        )

    def test_reward_summary_retries_a_transitional_counter_frame(self):
        backend = FakeBackend(
            [
                make_button(
                    "CommissionInfoUI4Mellow(Clone)",
                    "root/Overlay/UIMain/CommissionInfoUI4Mellow(Clone)",
                )
            ]
        )
        backend.ui_sequence = [
            make_ui([], generation=10),
            make_ui(
                [
                    make_text(
                        "1",
                        "root/CommissionInfoUI4Mellow(Clone)/frame/main/content/"
                        "event/frame/counter/finished/Text",
                    )
                ],
                generation=11,
            ),
        ]

        self.assertEqual(
            make_oracle(backend).reward_summary_count("commission", "finished"),
            1,
        )

    def test_reward_summary_zero_requires_exact_section_frame(self):
        backend = FakeBackend(
            [
                make_button(
                    "CommissionInfoUI4Mellow(Clone)",
                    "root/Overlay/UIMain/CommissionInfoUI4Mellow(Clone)",
                )
            ]
        )
        backend.ui = make_ui(
            [],
            images=[
                make_image(
                    "root/CommissionInfoUI4Mellow(Clone)/frame/main/content/"
                    "class/frame",
                    "frame_class",
                )
            ],
        )

        self.assertEqual(
            make_oracle(backend).reward_summary_count("tactical", "ongoing"),
            0,
        )

    def test_reward_go_button_is_distinct_from_finish_button(self):
        backend = FakeBackend(
            [
                make_button(
                    "CommissionInfoUI4Mellow(Clone)",
                    "root/Overlay/UIMain/CommissionInfoUI4Mellow(Clone)",
                    827,
                    622,
                    {"left": 0, "top": 0, "right": 1280, "bottom": 720},
                ),
                make_button(
                    "go_btn",
                    "root/CommissionInfoUI4Mellow(Clone)/frame/main/content/"
                    "event/frame/go_btn",
                    465,
                    294,
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertFalse(oracle.exists("reward/commission/finish"))
        self.assertTrue(oracle.enabled("reward/commission/go"))

    def test_commission_rows_are_built_from_exact_typed_fields(self):
        page = "root/UICamera/Canvas/UIMain/EventUI(Clone)"
        row = page + "/scrollRect$/content/0"
        backend = FakeBackend(
            [
                make_button(
                    "back_btn",
                    page + "/blur_panel/adapt/top/back_btn",
                    58,
                    53,
                ),
                make_button(
                    "bgNormal$",
                    row + "/bgNormal$",
                    640,
                    190,
                    {"left": 160, "top": 120, "right": 1120, "bottom": 255},
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("高阶自主训练", row + "/labelName$"),
                make_text("50", row + "/level/labelLv$"),
                make_text("10:00:00", row + "/labelTime$/Text"),
            ],
            images=[
                make_image(row + "/iconState$/0", "kongxian_bg"),
                make_image(row + "/iconType$", "jianduixunlian"),
            ],
        )

        rows = make_oracle(backend).commission_rows()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].index, 0)
        self.assertEqual(rows[0].name, "高阶自主训练")
        self.assertEqual(rows[0].level, 50)
        self.assertEqual(rows[0].duration_seconds, 10 * 60 * 60)
        self.assertEqual(rows[0].status, CommissionStatus.PENDING)
        self.assertEqual(rows[0].type_sprite, "jianduixunlian")
        self.assertEqual(
            rows[0].signature,
            (0, "高阶自主训练", 50, 10 * 60 * 60, "pending", "jianduixunlian"),
        )

    def test_commission_rows_retry_a_transitional_missing_image(self):
        page = "root/UICamera/Canvas/UIMain/EventUI(Clone)"
        row = page + "/scrollRect$/content/0"
        backend = FakeBackend(
            [
                make_button("back_btn", page + "/blur_panel/adapt/top/back_btn"),
                make_button("bgNormal$", row + "/bgNormal$", 640, 190),
            ]
        )
        texts = [
            make_text("高阶自主训练", row + "/labelName$"),
            make_text("50", row + "/level/labelLv$"),
            make_text("10:00:00", row + "/labelTime$/Text"),
        ]
        incomplete = make_ui(
            texts,
            images=[make_image(row + "/iconState$/0", "kongxian_bg")],
            generation=10,
        )
        complete = make_ui(
            texts,
            images=[
                make_image(row + "/iconState$/0", "kongxian_bg"),
                make_image(row + "/iconType$", "jianduixunlian"),
            ],
            generation=11,
        )
        backend.ui_sequence = [incomplete, complete]

        rows = make_oracle(backend).commission_rows()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].type_sprite, "jianduixunlian")

    def test_commission_scroll_uses_exact_handle_and_proves_row_change(self):
        backend = FakeBackend([])
        set_commission_scroll_view(
            backend,
            index=0,
            name="第一页委托",
            handle_top=75,
            generation=10,
        )

        def advance_scroll():
            set_commission_scroll_view(
                backend,
                index=1,
                name="第二页委托",
                handle_top=195,
                generation=11,
            )

        backend.on_swipe = advance_scroll
        oracle = make_oracle(backend)

        before = oracle.commission_scroll_state()
        proof = oracle.commission_scroll_next()

        self.assertTrue(before.scrollable)
        self.assertTrue(before.at_top)
        self.assertIsNotNone(proof)
        self.assertEqual(proof.direction, "next")
        self.assertEqual(proof.before_position, 0.0)
        self.assertEqual(proof.after_position, 1.0)
        self.assertNotEqual(
            proof.before_row_signatures,
            proof.after_row_signatures,
        )
        self.assertEqual(len(backend.swipes), 1)
        self.assertEqual(backend.swipes[0][0], backend.swipes[0][2])
        self.assertEqual(backend.swipes[0][4], 500)

    def test_commission_scroll_refuses_handle_without_top_raycast(self):
        backend = FakeBackend([])
        set_commission_scroll_view(
            backend,
            index=0,
            name="第一页委托",
            handle_top=75,
            generation=10,
            handle_raycast_top=False,
        )

        with self.assertRaisesRegex(SemanticGateClosed, "top-raycastable"):
            make_oracle(backend).commission_scroll_next()

        self.assertEqual(backend.swipes, [])

    def test_commission_scroll_exact_absence_is_a_single_page_state(self):
        backend = FakeBackend([])
        set_commission_scroll_view(
            backend,
            index=0,
            name="单页委托",
            handle_top=75,
            generation=10,
        )
        backend.ui["images"] = backend.ui["images"][:2]
        backend.ui["image_count"] = 2

        state = make_oracle(backend).commission_scroll_state()

        self.assertFalse(state.scrollable)
        self.assertTrue(state.at_top)
        self.assertTrue(state.at_bottom)
        self.assertEqual(state.handle_path, "")

    def test_commission_scroll_refuses_partial_track_handle_pair(self):
        backend = FakeBackend([])
        set_commission_scroll_view(
            backend,
            index=0,
            name="单页委托",
            handle_top=75,
            generation=10,
        )
        backend.ui["images"] = backend.ui["images"][:-1]
        backend.ui["image_count"] -= 1

        with self.assertRaisesRegex(SemanticGateClosed, "absent or ambiguous"):
            make_oracle(backend).commission_scroll_state()

    def test_commission_scroll_does_not_treat_countdown_tick_as_new_page(self):
        backend = FakeBackend([])
        set_commission_scroll_view(
            backend,
            index=0,
            name="运行中委托",
            handle_top=75,
            generation=10,
            duration="01:00:00",
        )

        def countdown_only():
            set_commission_scroll_view(
                backend,
                index=0,
                name="运行中委托",
                handle_top=135,
                generation=11,
                duration="00:59:59",
            )

        backend.on_swipe = countdown_only

        self.assertIsNone(make_oracle(backend).commission_scroll_next())
        self.assertEqual(len(backend.swipes), 1)

    def test_commission_scroll_to_top_proves_reverse_row_change(self):
        backend = FakeBackend([])
        set_commission_scroll_view(
            backend,
            index=1,
            name="第二页委托",
            handle_top=195,
            generation=10,
        )

        def return_to_top():
            set_commission_scroll_view(
                backend,
                index=0,
                name="第一页委托",
                handle_top=75,
                generation=11,
            )

        backend.on_swipe = return_to_top
        proof = make_oracle(backend).commission_scroll_to_top()

        self.assertIsNotNone(proof)
        self.assertEqual(proof.direction, "top")
        self.assertEqual(proof.before_position, 1.0)
        self.assertEqual(proof.after_position, 0.0)

    def test_commission_scroll_to_top_repeats_until_exact_top(self):
        backend = FakeBackend([])
        set_commission_scroll_view(
            backend,
            index=1,
            name="第二页委托",
            handle_top=195,
            generation=10,
        )
        steps = iter(((135, 11), (75, 12)))

        def return_towards_top():
            handle_top, generation = next(steps)
            set_commission_scroll_view(
                backend,
                index=0 if handle_top == 75 else 1,
                name="第一页委托" if handle_top == 75 else "第二页委托",
                handle_top=handle_top,
                generation=generation,
            )

        backend.on_swipe = return_towards_top
        proof = make_oracle(backend).commission_scroll_to_top()

        self.assertEqual(proof.before_position, 1.0)
        self.assertEqual(proof.after_position, 0.0)
        self.assertEqual(len(backend.swipes), 2)

    def test_commission_row_click_revalidates_exact_typed_signature(self):
        page = "root/UICamera/Canvas/UIMain/EventUI(Clone)"
        row = page + "/scrollRect$/content/0"
        backend = FakeBackend(
            [
                make_button("back_btn", page + "/blur_panel/adapt/top/back_btn"),
                make_button("bgNormal$", row + "/bgNormal$", 640, 190),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("高阶自主训练", row + "/labelName$"),
                make_text("50", row + "/level/labelLv$"),
                make_text("10:00:00", row + "/labelTime$/Text"),
            ],
            images=[
                make_image(row + "/iconState$/0", "kongxian_bg"),
                make_image(row + "/iconType$", "jianduixunlian"),
            ],
        )
        oracle = make_oracle(backend)
        signature = oracle.commission_rows()[0].signature

        receipt = oracle.click_commission_row(signature)

        self.assertEqual(receipt.semantic_id, "commission/row/0")
        self.assertEqual(backend.taps, [(640, 190)])
        with self.assertRaises(SemanticGateClosed):
            oracle.click_commission_row((0, "另一个委托", 50, 36000, "pending", "x"))
        self.assertEqual(backend.taps, [(640, 190)])

    def test_commission_running_row_uses_reviewed_ongoing_marker(self):
        page = "root/UICamera/Canvas/UIMain/EventUI(Clone)"
        row = page + "/scrollRect$/content/0"
        backend = FakeBackend(
            [
                make_button("back_btn", page + "/blur_panel/adapt/top/back_btn"),
                make_button("bgNormal$", row + "/bgNormal$", 640, 190),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("高阶战术研发II", row + "/labelName$"),
                make_text("50", row + "/level/labelLv$"),
                make_text("01:58:44", row + "/labelTime$/Text"),
            ],
            images=[
                make_image(row + "/iconState$/1", "tag_ongoing"),
                make_image(row + "/iconType$", "faxiankuangmai"),
            ],
        )

        rows = make_oracle(backend).commission_rows()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].status, CommissionStatus.RUNNING)
        self.assertEqual(rows[0].duration_seconds, 7124)

    def test_commission_detail_recommend_requires_exact_selected_identity(self):
        root = "root/Overlay/UIMain/blur_panel/"
        detail = root + "scrollItem/maskDetail/detailPanel/"
        buttons = [
            make_button("back_btn", root + "adapt/top/back_btn", 58, 53),
            make_button("btn_recommend", detail + "btn_recommend", 935, 363),
            make_button("btn", detail + "btn", 1092, 363),
        ]
        for side in ("left", "right"):
            for slot in range(1, 4):
                buttons.append(
                    make_button(
                        "emptytpl",
                        detail
                        + "frame/ship_contain_{0}/ship_{1}/emptytpl".format(
                            side, slot
                        ),
                    )
                )
        backend = FakeBackend(buttons)
        base = "root/Overlay/UIMain/blur_panel/scrollItem/"
        backend.ui = make_ui(
            [
                make_text("日常资源开发III", base + "labelName$"),
                make_text("15", base + "level/labelLv$"),
                make_text("01:00:00", base + "labelTime$/Text"),
                make_text("0", base + "maskDetail/detailPanel/consume/Text"),
            ]
        )
        oracle = make_oracle(backend)
        signature = (1, "日常资源开发III", 15, 3600, "pending", "faxiankuangmai")

        state = oracle.commission_detail_state()
        receipt = oracle.click_commission_recommend(signature)

        self.assertEqual(state.selected_ship_count, 0)
        self.assertEqual(state.empty_ship_count, 6)
        self.assertEqual(state.oil_cost, 0)
        self.assertEqual(receipt.semantic_id, "commission/detail/recommend")
        self.assertEqual(backend.taps, [(935, 363)])
        with self.assertRaises(SemanticGateClosed):
            oracle.click_commission_start(signature)
        self.assertEqual(backend.taps, [(935, 363)])

    def test_commission_start_proof_requires_exact_non_pending_countdown_row(self):
        page = "root/UICamera/Canvas/UIMain/EventUI(Clone)"
        row = page + "/scrollRect$/content/1"
        backend = FakeBackend(
            [
                make_button("back_btn", page + "/blur_panel/adapt/top/back_btn"),
                make_button("bgNormal$", row + "/bgNormal$", 640, 190),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("日常资源开发III", row + "/labelName$"),
                make_text("15", row + "/level/labelLv$"),
                make_text("00:59:55", row + "/labelTime$/Text"),
            ],
            images=[
                make_image(row + "/iconState$/1", "tag_ongoing"),
                make_image(row + "/iconType$", "faxiankuangmai"),
            ],
        )
        signature = (1, "日常资源开发III", 15, 3600, "pending", "faxiankuangmai")

        proof = make_oracle(backend).commission_start_transition(signature)

        self.assertEqual(proof.before_duration_seconds, 3600)
        self.assertEqual(proof.after_duration_seconds, 3595)
        self.assertEqual(proof.before_status_sprite, "kongxian_bg")
        self.assertEqual(proof.after_status_sprite, "tag_ongoing")

    def test_commission_start_proof_accepts_exact_running_detail(self):
        root = "root/Overlay/UIMain/blur_panel/"
        backend = FakeBackend(
            [make_button("back_btn", root + "adapt/top/back_btn", 58, 53)]
        )
        base = root + "scrollItem"
        backend.ui = make_ui(
            [
                make_text("高阶战术研发II", base + "/labelName$"),
                make_text("50", base + "/level/labelLv$"),
                make_text("01:58:44", base + "/labelTime$/Text"),
                make_text(
                    "取消",
                    base + "/maskDetail/detailPanel/btn/giveup/text",
                ),
            ],
            images=[
                make_image(base + "/iconState$/1", "tag_ongoing"),
                make_image(base + "/iconType$", "faxiankuangmai"),
            ],
        )
        signature = (3, "高阶战术研发II", 50, 7200, "pending", "faxiankuangmai")

        proof = make_oracle(backend).commission_start_transition(signature)

        self.assertEqual(proof.name, "高阶战术研发II")
        self.assertEqual(proof.after_duration_seconds, 7124)
        self.assertEqual(proof.after_status_sprite, "tag_ongoing")

    def test_commission_start_rejects_nonzero_oil_cost(self):
        root = "root/Overlay/UIMain/blur_panel/"
        detail = root + "scrollItem/maskDetail/detailPanel/"
        backend = FakeBackend(
            [
                make_button("back_btn", root + "adapt/top/back_btn", 58, 53),
                make_button("btn_recommend", detail + "btn_recommend", 935, 363),
                make_button("btn", detail + "btn", 1092, 363),
            ]
        )
        base = "root/Overlay/UIMain/blur_panel/scrollItem/"
        backend.ui = make_ui(
            [
                make_text("日常资源开发III", base + "labelName$"),
                make_text("15", base + "level/labelLv$"),
                make_text("01:00:00", base + "labelTime$/Text"),
                make_text("10", base + "maskDetail/detailPanel/consume/Text"),
            ]
        )
        signature = (1, "日常资源开发III", 15, 3600, "pending", "faxiankuangmai")

        with self.assertRaises(SemanticGateClosed):
            make_oracle(backend).click_commission_start(signature)
        self.assertEqual(backend.taps, [])

    def test_commission_unknown_status_sprite_fails_closed(self):
        page = "root/UICamera/Canvas/UIMain/EventUI(Clone)"
        row = page + "/scrollRect$/content/0"
        backend = FakeBackend(
            [
                make_button("back_btn", page + "/blur_panel/adapt/top/back_btn"),
                make_button("bgNormal$", row + "/bgNormal$"),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("未知委托", row + "/labelName$"),
                make_text("1", row + "/level/labelLv$"),
                make_text("01:00:00", row + "/labelTime$/Text"),
            ],
            images=[
                make_image(row + "/iconState$/0", "unreviewed_state"),
                make_image(row + "/iconType$", "unknown_type"),
            ],
        )

        with self.assertRaises(SemanticGateClosed):
            make_oracle(backend).commission_rows()

    def test_commission_rows_exclude_buttons_outside_the_viewport(self):
        page = "root/UICamera/Canvas/UIMain/EventUI(Clone)"
        row = page + "/scrollRect$/content/4"
        backend = FakeBackend(
            [
                make_button("back_btn", page + "/blur_panel/adapt/top/back_btn"),
                make_button(
                    "bgNormal$",
                    row + "/bgNormal$",
                    640,
                    736,
                    {"left": 160, "top": 668, "right": 1120, "bottom": 804},
                ),
            ]
        )
        backend.ui = make_ui([])

        with self.assertRaisesRegex(
            SemanticGateClosed,
            "no actionable typed rows",
        ):
            make_oracle(backend).commission_rows()

    def test_commission_empty_requires_explicit_typed_marker(self):
        page = "root/UICamera/Canvas/UIMain/EventUI(Clone)"
        backend = FakeBackend(
            [make_button("back_btn", page + "/blur_panel/adapt/top/back_btn")]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "暂无可以进行的委托",
                    page + "/empty/Text",
                    {"left": 100, "top": 278, "right": 1200, "bottom": 441},
                )
            ]
        )

        self.assertTrue(make_oracle(backend).commission_is_empty())

    def test_commission_rows_accept_only_the_explicit_empty_marker(self):
        page = "root/UICamera/Canvas/UIMain/EventUI(Clone)"
        backend = FakeBackend(
            [make_button("back_btn", page + "/blur_panel/adapt/top/back_btn")]
        )
        oracle = make_oracle(backend)

        with self.assertRaises(SemanticGateClosed):
            oracle.commission_rows()

        backend.ui = make_ui(
            [
                make_text(
                    "暂无可以进行的委托",
                    page + "/empty/Text",
                    {"left": 100, "top": 278, "right": 1200, "bottom": 441},
                )
            ]
        )
        self.assertEqual(oracle.commission_rows(), ())

    def test_commission_absence_is_not_empty(self):
        page = "root/UICamera/Canvas/UIMain/EventUI(Clone)"
        backend = FakeBackend(
            [make_button("back_btn", page + "/blur_panel/adapt/top/back_btn")]
        )

        self.assertFalse(make_oracle(backend).commission_is_empty())

    def test_happy_path_exposes_bounds_and_clicks_center(self):
        backend = FakeBackend(
            [
                make_button(
                    "settings",
                    "UICamera/Canvas/UIOrigin/Main/frame/top/btns/settings",
                    1221.0,
                    36.0,
                    {"left": 1202.0, "top": 17.0, "right": 1240.0, "bottom": 55.0},
                )
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.exists("main/settings"))
        self.assertTrue(oracle.enabled("main/settings"))
        self.assertEqual(oracle.bounds("main/settings").left, 1202.0)
        receipt = oracle.click("main/settings")

        self.assertEqual(receipt.path.split("/")[-1], "settings")
        self.assertEqual(backend.taps, [(1221, 36)])

    def test_enabled_retries_a_truncated_button_transition_frame(self):
        button = make_button(
            "settings",
            "UICamera/Canvas/UIOrigin/Main/frame/top/btns/settings",
            1221,
            36,
        )
        backend = FakeBackend([button])
        incomplete = make_buttons([button], generation=10)
        incomplete["truncated"] = True
        backend.buttons_sequence = [
            incomplete,
            make_buttons([button], generation=11),
        ]

        self.assertTrue(make_oracle(backend).enabled("main/settings"))

    def test_unknown_mapping_fails_closed_without_input(self):
        backend = FakeBackend([])
        oracle = make_oracle(backend)

        with self.assertRaises(SemanticGateClosed):
            oracle.click("main/not-mapped")
        self.assertEqual(backend.taps, [])

    def test_wrong_foreground_fails_closed_without_input(self):
        backend = FakeBackend(
            [make_button("settings", "root/frame/top/btns/settings", 1221, 36)]
        )
        backend.foreground = "com.android.launcher3/.QuickstepLauncher"
        oracle = make_oracle(backend)

        with self.assertRaises(SemanticGateClosed):
            oracle.click("main/settings")
        self.assertEqual(backend.taps, [])

    def test_stale_snapshot_fails_closed(self):
        backend = FakeBackend(
            [make_button("settings", "root/frame/top/btns/settings", 1221, 36)]
        )
        backend.buttons["age_ms"] = 3000
        oracle = make_oracle(backend)

        with self.assertRaises(SemanticGateClosed):
            oracle.enabled("main/settings")

    def test_duplicate_target_is_ambiguous(self):
        button = make_button("settings", "root/frame/top/btns/settings", 1221, 36)
        backend = FakeBackend([button, copy.deepcopy(button)])
        oracle = make_oracle(backend)

        with self.assertRaises(SemanticGateClosed):
            oracle.click("main/settings")
        self.assertEqual(backend.taps, [])

    def test_missing_bounds_fails_closed(self):
        button = make_button("settings", "root/frame/top/btns/settings", 1221, 36)
        button["adb_bounds"] = None
        backend = FakeBackend([button])
        oracle = make_oracle(backend)

        self.assertFalse(oracle.enabled("main/settings"))
        with self.assertRaises(SemanticGateClosed):
            oracle.click("main/settings")
        self.assertEqual(backend.taps, [])

    def test_non_top_raycast_target_fails_closed(self):
        backend = FakeBackend(
            [
                make_button(
                    "settings",
                    "root/frame/top/btns/settings",
                    1221,
                    36,
                    raycast_top=False,
                )
            ]
        )
        oracle = make_oracle(backend)

        self.assertFalse(oracle.enabled("main/settings"))
        with self.assertRaises(SemanticGateClosed):
            oracle.click("main/settings")
        self.assertEqual(backend.taps, [])

    def test_unrelated_zero_area_button_does_not_poison_valid_target(self):
        zero_area = make_button("layout", "root/layout")
        zero_area["adb_bounds"] = {
            "left": 100,
            "top": 100,
            "right": 100,
            "bottom": 100,
        }
        backend = FakeBackend(
            [
                zero_area,
                make_button("settings", "root/frame/top/btns/settings", 1221, 36),
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.enabled("main/settings"))
        self.assertEqual(backend.taps, [])

    def test_loading_blocker_prevents_unrelated_click(self):
        backend = FakeBackend(
            [
                make_button("settings", "root/frame/top/btns/settings", 1221, 36),
                make_button("Loading(Clone)", "root/UIOverlay/Loading(Clone)"),
            ]
        )
        oracle = make_oracle(backend)

        with self.assertRaises(SemanticGateClosed):
            oracle.click("main/settings")
        self.assertEqual(backend.taps, [])

    def test_bulletin_blocks_main_but_allows_mapped_close(self):
        backend = FakeBackend(
            [
                make_button("settings", "root/frame/top/btns/settings", 1221, 36),
                make_button(
                    "close_btn",
                    "Overlay/UIMain/NewBulletinBoardUI(Clone)/bg/close_btn",
                    1204,
                    83,
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertFalse(oracle.enabled("main/settings"))
        self.assertTrue(oracle.enabled("overlay/bulletin/close"))
        with self.assertRaises(SemanticGateClosed):
            oracle.click("main/settings")
        receipt = oracle.click("overlay/bulletin/close")

        self.assertEqual(receipt.semantic_id, "overlay/bulletin/close")
        self.assertEqual(backend.taps, [(1204, 83)])

    def test_guild_message_blocks_main_but_allows_exact_close(self):
        backend = FakeBackend(
            [
                make_button("task", "root/frame/bottom/frame/task", 875, 684),
                make_button(
                    "close",
                    "Overlay/UIMain/GuildMsgBoxUI(Clone)/frame/close",
                    1150,
                    90,
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertFalse(oracle.enabled("main/task"))
        self.assertTrue(oracle.enabled("overlay/guild-message/close"))
        with self.assertRaises(SemanticGateClosed):
            oracle.click("main/task")
        receipt = oracle.click("overlay/guild-message/close")

        self.assertEqual(receipt.semantic_id, "overlay/guild-message/close")
        self.assertEqual(backend.taps, [(1150, 90)])

    def test_task_page_blocks_main_but_allows_exact_back(self):
        backend = FakeBackend(
            [
                make_button("task", "root/frame/bottom/frame/task", 875, 684),
                make_button(
                    "back_btn",
                    "root/TaskScene(Clone)/blur_panel/adapt/top/back_btn",
                    58,
                    53,
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertFalse(oracle.enabled("main/task"))
        self.assertTrue(oracle.enabled("task/page/back"))
        with self.assertRaises(SemanticGateClosed):
            oracle.click("main/task")
        receipt = oracle.click("task/page/back")

        self.assertEqual(receipt.semantic_id, "task/page/back")
        self.assertEqual(backend.taps, [(58, 53)])

    def test_award_info_blocks_task_page_but_allows_exact_close(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_btn",
                    "root/TaskScene(Clone)/blur_panel/adapt/top/back_btn",
                    58,
                    53,
                ),
                make_button(
                    "close",
                    "root/AwardInfoUI(Clone)/items/close",
                    640,
                    650,
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertFalse(oracle.enabled("task/page/back"))
        self.assertTrue(oracle.enabled("reward/award-info/close"))
        with self.assertRaises(SemanticGateClosed):
            oracle.click("task/page/back")
        receipt = oracle.click("reward/award-info/close")

        self.assertEqual(receipt.semantic_id, "reward/award-info/close")
        self.assertEqual(backend.taps, [(640, 650)])

    def test_ship_exp_blocks_reward_page_but_allows_exact_skip_layer(self):
        backend = FakeBackend(
            [
                make_button(
                    "finish_btn",
                    "root/CommissionInfoUI4Mellow(Clone)/frame/main/content/"
                    "event/frame/finish_btn",
                    465,
                    294,
                ),
                make_button(
                    "skipLayer",
                    "root/ShipExpUI(Clone)/skipLayer",
                    640,
                    360,
                    {"left": 0, "top": 0, "right": 1280, "bottom": 720},
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertFalse(oracle.enabled("reward/commission"))
        self.assertTrue(oracle.enabled("reward/ship-exp/close"))
        with self.assertRaises(SemanticGateClosed):
            oracle.click("reward/commission")
        receipt = oracle.click("reward/ship-exp/close")

        self.assertEqual(receipt.path, "root/ShipExpUI(Clone)/skipLayer")
        self.assertEqual(backend.taps, [(640, 360)])

    def test_generation_rollback_fails_closed(self):
        backend = FakeBackend([])
        oracle = make_oracle(backend)
        oracle.read_state()
        backend.snapshot["generation"] = 9
        backend.buttons["generation"] = 9

        with self.assertRaises(SemanticGateClosed):
            oracle.read_state()

    def test_click_and_wait_requires_a_new_generation(self):
        backend = FakeBackend(
            [make_button("settings", "root/frame/top/btns/settings", 1221, 36)]
        )

        def transition():
            backend.snapshot["generation"] = 11
            backend.buttons = make_buttons(
                [
                    make_button(
                        "back_btn",
                        "root/NewSettingsUI(Clone)/blur_panel/adapt/top/back_btn",
                        73,
                        42,
                    )
                ],
                generation=11,
            )

        backend.on_tap = transition
        oracle = make_oracle(backend)

        target = oracle.click_and_wait("main/settings", "settings/back", 1.0)

        self.assertEqual(target.name, "back_btn")
        self.assertEqual(backend.taps, [(1221, 36)])

    def test_mission_unfinished_state_requires_reviewed_go_button(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_btn",
                    "root/TaskScene(Clone)/blur_panel/adapt/top/back_btn",
                    58,
                    53,
                ),
                make_button(
                    "go_btn",
                    "root/TaskScene(Clone)/pages/TaskListPage(Clone)/"
                    "right_panel/content/0/frame/go_btn",
                    1170,
                    158,
                ),
            ]
        )

        state = make_oracle(backend).mission_page_state()

        self.assertEqual(state.disposition, MissionDisposition.UNFINISHED)
        self.assertEqual(len(state.unfinished_rows), 1)
        self.assertEqual(state.claim_rows, ())

    def test_mission_claim_all_takes_precedence(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_btn",
                    "root/TaskScene(Clone)/blur_panel/adapt/top/back_btn",
                    58,
                    53,
                ),
                make_button(
                    "GetAllButton",
                    "root/TaskScene(Clone)/blur_panel/adapt/top/GetAllButton",
                    1080,
                    40,
                ),
                make_button(
                    "get_btn",
                    "root/TaskScene(Clone)/pages/TaskListPage(Clone)/"
                    "right_panel/content/0/frame/get_btn",
                    1170,
                    158,
                ),
            ]
        )

        state = make_oracle(backend).mission_page_state()

        self.assertEqual(state.disposition, MissionDisposition.CLAIMABLE_ALL)
        self.assertIsNotNone(state.claim_all)

    def test_mission_row_claims_are_ordered_by_runtime_index(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_btn",
                    "root/TaskScene(Clone)/blur_panel/adapt/top/back_btn",
                    58,
                    53,
                ),
                make_button(
                    "get_btn",
                    "root/TaskScene(Clone)/pages/TaskListPage(Clone)/"
                    "right_panel/content/3/frame/get_btn",
                    1170,
                    620,
                ),
                make_button(
                    "get_btn",
                    "root/TaskScene(Clone)/pages/TaskListPage(Clone)/"
                    "right_panel/content/1/frame/get_btn",
                    1170,
                    310,
                ),
            ]
        )

        state = make_oracle(backend).mission_page_state()

        self.assertEqual(state.disposition, MissionDisposition.CLAIMABLE_ROW)
        self.assertIn("content/1/", state.claim_rows[0].path)
        self.assertIn("content/3/", state.claim_rows[1].path)

    def test_mission_absence_is_unknown_not_empty(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_btn",
                    "root/TaskScene(Clone)/blur_panel/adapt/top/back_btn",
                    58,
                    53,
                )
            ]
        )

        state = make_oracle(backend).mission_page_state()

        self.assertEqual(state.disposition, MissionDisposition.UNKNOWN)

    def test_mission_duplicate_runtime_row_fails_closed(self):
        row = make_button(
            "get_btn",
            "root/TaskScene(Clone)/pages/TaskListPage(Clone)/"
            "right_panel/content/0/frame/get_btn",
            1170,
            158,
        )
        backend = FakeBackend(
            [
                make_button(
                    "back_btn",
                    "root/TaskScene(Clone)/blur_panel/adapt/top/back_btn",
                    58,
                    53,
                ),
                row,
                copy.deepcopy(row),
            ]
        )

        with self.assertRaises(SemanticGateClosed):
            make_oracle(backend).mission_page_state()

    def test_mission_wait_requires_increasing_generations(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_btn",
                    "root/TaskScene(Clone)/blur_panel/adapt/top/back_btn",
                    58,
                    53,
                ),
                make_button(
                    "go_btn",
                    "root/TaskScene(Clone)/pages/TaskListPage(Clone)/"
                    "right_panel/content/0/frame/go_btn",
                    1170,
                    158,
                ),
            ]
        )
        oracle = make_oracle(backend)

        with self.assertRaises(SemanticGateClosed):
            oracle.wait_for_mission_state(
                timeout_seconds=0.001,
                interval_seconds=0,
            )

    def test_mission_wait_accepts_same_signature_on_new_generation(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_btn",
                    "root/TaskScene(Clone)/blur_panel/adapt/top/back_btn",
                    58,
                    53,
                ),
                make_button(
                    "go_btn",
                    "root/TaskScene(Clone)/pages/TaskListPage(Clone)/"
                    "right_panel/content/0/frame/go_btn",
                    1170,
                    158,
                ),
            ]
        )
        oracle = make_oracle(backend)

        def advance_generation(_):
            generation = backend.snapshot["generation"] + 1
            backend.snapshot["generation"] = generation
            backend.buttons["generation"] = generation
            backend.ui["generation"] = generation

        oracle._sleep = advance_generation

        state = oracle.wait_for_mission_state(
            timeout_seconds=1,
            interval_seconds=0,
        )

        self.assertEqual(state.disposition, MissionDisposition.UNFINISHED)
        self.assertEqual(state.generation, 11)

    def test_typed_text_is_selected_by_ocr_bounds(self):
        backend = FakeBackend([])
        backend.ui = make_ui(
            [
                make_text("01:23:45", "root/timer"),
                make_text(
                    "outside",
                    "root/outside",
                    {"left": 500.0, "top": 500.0, "right": 600.0, "bottom": 540.0},
                    kind="tmp-text",
                ),
            ]
        )
        oracle = make_oracle(backend)

        matches = oracle.texts_in_bounds(Bounds(90, 90, 200, 150))

        self.assertEqual([item.text for item in matches], ["01:23:45"])
        self.assertEqual(matches[0].kind, "ugui-text")

    def test_typed_text_snapshot_truncation_fails_closed(self):
        backend = FakeBackend([])
        backend.ui = make_ui([make_text("12")])
        backend.ui["text_truncated"] = True

        with self.assertRaises(SemanticGateClosed):
            make_oracle(backend).read_ui_state()

    def test_typed_image_exposes_sprite_color_and_bounds(self):
        backend = FakeBackend([])
        backend.ui = make_ui([], images=[make_image("root/red_dot", "red_dot")])

        state = make_oracle(backend).read_ui_state()

        self.assertEqual(state.images[0].sprite, "red_dot")
        self.assertEqual(state.images[0].color, (1.0, 0.5, 0.25, 1.0))
        self.assertEqual(state.images[0].bounds, Bounds(200, 100, 240, 140))

    def test_typed_mission_nav_image_is_selected_and_actionable(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_btn",
                    "root/TaskScene(Clone)/blur_panel/adapt/top/back_btn",
                    58,
                    53,
                )
            ]
        )
        image = make_image(
            "root/TaskScene(Clone)/blur_panel/adapt/left_length/frame/"
            "tagRoot/all/selected/Image",
            "icon_all_sel",
            {"left": 0.0, "top": 100.0, "right": 100.0, "bottom": 200.0},
        )
        image["raycast_target"] = True
        image["raycast_top"] = True
        backend.ui = make_ui([], images=[image])
        oracle = make_oracle(backend)

        self.assertTrue(oracle.image_selected("task/nav/all"))
        receipt = oracle.click_image("task/nav/all")

        self.assertEqual(receipt.semantic_id, "task/nav/all")
        self.assertEqual(backend.taps, [(50, 150)])

    def test_typed_commission_nav_uses_commission_page_identity(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_btn",
                    "root/EventUI(Clone)/blur_panel/adapt/top/back_btn",
                    58,
                    53,
                )
            ]
        )
        image = make_image(
            "root/EventUI(Clone)/blur_panel/adapt/left_length/frame/scroll_rect/"
            "tagRoot/daily_btn/selected/Image",
            "toggle_meiri_sel 1",
            {"left": 0.0, "top": 100.0, "right": 100.0, "bottom": 200.0},
        )
        image["raycast_target"] = True
        image["raycast_top"] = True
        backend.ui = make_ui([], images=[image])
        oracle = make_oracle(backend)

        self.assertTrue(oracle.image_selected("commission/nav/daily"))
        receipt = oracle.click_image("commission/nav/daily")

        self.assertEqual(receipt.semantic_id, "commission/nav/daily")
        self.assertEqual(backend.taps, [(50, 150)])

    def test_image_state_retries_a_truncated_transition_frame(self):
        backend = FakeBackend([])
        image = make_image(
            "root/EventUI(Clone)/blur_panel/adapt/left_length/frame/scroll_rect/"
            "tagRoot/daily_btn/selected/Image",
            "toggle_meiri_sel 1",
        )
        incomplete = make_ui([], images=[image], generation=10)
        incomplete["image_truncated"] = True
        backend.ui_sequence = [
            incomplete,
            make_ui([], images=[image], generation=11),
        ]

        self.assertTrue(make_oracle(backend).image_selected("commission/nav/daily"))

    def test_typed_text_record_truncation_is_scoped_to_the_record(self):
        backend = FakeBackend([])
        text = make_text("12")
        text["flags"] |= 0x10
        backend.ui = make_ui([text])

        state = make_oracle(backend).read_ui_state()

        self.assertTrue(state.texts[0].truncated)


if __name__ == "__main__":
    unittest.main()
