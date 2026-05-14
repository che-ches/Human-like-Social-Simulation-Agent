"""
真人社交模拟智能体 — CLI

运行：
  python main.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent
CHAT_LOG_DIR = PROJECT_DIR / "chat_logs"

# ANSI 颜色（用于输入和对话颜色区分）
ANSI_LIGHT_GREEN = "\033[92m"  # 提示词
ANSI_MAGENTA = "\033[95m"  # 用户输入
ANSI_CYAN = "\033[96m"  # AI与对话内容
ANSI_YELLOW = "\033[93m"  # AI回复例外
ANSI_RESET = "\033[0m"


def _load_env() -> None:
    try:
        from dotenv import load_dotenv

        env_path = PROJECT_DIR / ".env"
        env_example_path = PROJECT_DIR / ".env.example"
        if env_path.exists():
            load_dotenv(str(env_path), override=True)
        elif env_example_path.exists():
            load_dotenv(str(env_example_path), override=False)
    except Exception:
        pass


def _now_display() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _new_log_path() -> Path:
    CHAT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = CHAT_LOG_DIR / f"chat_{stamp}.log"
    index = 1
    while candidate.exists():
        candidate = CHAT_LOG_DIR / f"chat_{stamp}_{index}.log"
        index += 1
    return candidate


def _state_to_dict(state: "GameState") -> dict[str, Any]:
    return {
        "relationship_score": state.relationship_score,
        "cumulative_net_points": state.cumulative_net_points,
        "turns": state.turns,
        "consecutive_negative_emotion_turns": state.consecutive_negative_emotion_turns,
        "recent_compliment_turns": state.recent_compliment_turns,
        "recent_user_texts": list(state.recent_user_texts),
        "ai_role": state.ai_role,
        "user_goal": state.user_goal,
    }


def _state_from_dict(data: dict[str, Any] | None) -> "GameState":
    from social_sim import GameState  # type: ignore[reportMissingImports]

    if not isinstance(data, dict):
        return GameState()

    recent_user_texts = data.get("recent_user_texts", [])
    if not isinstance(recent_user_texts, list):
        recent_user_texts = []

    return GameState(
        relationship_score=int(data.get("relationship_score", 5)),
        cumulative_net_points=int(data.get("cumulative_net_points", 0)),
        turns=int(data.get("turns", 0)),
        consecutive_negative_emotion_turns=int(data.get("consecutive_negative_emotion_turns", 0)),
        recent_compliment_turns=int(data.get("recent_compliment_turns", 0)),
        recent_user_texts=[str(x) for x in recent_user_texts][-6:],
        ai_role=str(data.get("ai_role", "")),
        user_goal=str(data.get("user_goal", "")),
    )


def _extract_json_payload(line: str, marker: str) -> dict[str, Any] | None:
    if marker not in line:
        return None
    payload = line.split(marker, 1)[1].strip()
    try:
        data = json.loads(payload)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _load_state_from_log(log_path: Path) -> "GameState":
    last_state: dict[str, Any] | None = None
    try:
        with log_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                payload = _extract_json_payload(line, "STATE_JSON: ")
                if payload is not None:
                    last_state = payload
    except Exception:
        pass
    return _state_from_dict(last_state)


def _preview_text(text: str, limit: int = 18) -> str:
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return "暂无内容"
    return cleaned if len(cleaned) <= limit else cleaned[:limit] + "..."


def _auto_initial_relationship_score(ai_role: str, user_goal: str) -> tuple[int, str]:
    text = f"{ai_role} {user_goal}".lower()

    # 关键词示例（为AI评分提供参考，但不绝对）
    examples = [
        ("警察", "审讯", 3, "司法对立场景，预设警惕"),
        ("普通人", "推销", 4, "有点厌烦，但不绝对"),
        ("普通人", "借钱", 4, "人性趋利避害"),
        ("普通人", "请教", 5, "事情较小，没有明显利害冲突"),
        ("网友", "闲聊", 5, "没有第一印象"),
        ("久别", "老友", 6, "情感纽带强"),
        ("曾经的同学", "", 6, "熟悉关系"),
        ("分手的恋人", "", 6, "曾经有好的回忆"),
    ]

    for role_key, goal_key, score, reason in examples:
        if role_key in text and (not goal_key or goal_key in text):
            return min(max(score, 3), 6), f"匹配示例：{role_key}/{goal_key} -> {score}，理由：{reason}"

    positive_keywords = ["老友", "同学", "兄弟", "姐妹", "朋友", "亲密", "熟悉", "信任", "合作", "支持"]
    neutral_keywords = ["同事", "邻居", "业务", "工作", "合作", "初次", "认识", "交流"]
    negative_keywords = ["陌生", "敌人", "对手", "警惕", "戒备", "审讯", "冲突", "对立", "怀疑", "不信任"]

    score_base = 5
    positive_hits = sum(1 for k in positive_keywords if k in text)
    neutral_hits = sum(1 for k in neutral_keywords if k in text)
    negative_hits = sum(1 for k in negative_keywords if k in text)

    score = score_base + min(2, positive_hits) - min(2, negative_hits)

    if positive_hits >= 2 and negative_hits == 0:
        reason = "多次出现熟悉／信任词，倾向上限。"
    elif negative_hits >= 2 and positive_hits == 0:
        reason = "多次出现敌对／戒备词，倾向下限。"
    elif positive_hits and negative_hits:
        reason = "存在混合信号，取中间值。"
    elif neutral_hits and not positive_hits and not negative_hits:
        reason = "中性场景，默认普通朋友。"
    else:
        reason = "无明显冲突或亲密词，依据默认值。"

    final_score = min(max(score, 3), 6)
    if final_score == 3:
        reason = "最终判定为低关系（3），场景为较高警惕/陌生。" if negative_hits else reason
    elif final_score == 6:
        reason = "最终判定为高关系（6），场景为熟悉/亲密。" if positive_hits else reason

    return final_score, reason


def _relationship_description(score: int) -> str:
    if score <= 2:
        return "强烈负面（敌意/不信任）"
    if score <= 4:
        return "偏负面（保留/疏离）"
    if score <= 6:
        return "中性（谨慎/观察）"
    if score <= 8:
        return "偏正面（合作/友好）"
    return "强烈正面（信任/亲近）"


def _summarize_log(log_path: Path) -> dict[str, Any]:
    turns = 0
    relationship_score: int | str = "-"
    last_user_text = "暂无内容"

    try:
        with log_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if "] 你：" in line:
                    turns += 1
                    last_user_text = line.split("你：", 1)[1].strip()
                payload = _extract_json_payload(line, "STATE_JSON: ")
                if payload is not None:
                    turns = int(payload.get("turns", turns))
                    relationship_score = payload.get("relationship_score", relationship_score)
    except Exception:
        pass

    modified = datetime.fromtimestamp(log_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")

    # 添加关系分描述
    def get_relationship_description(score: int | str) -> str:
        if isinstance(score, str) or score == "-":
            return "-"
        if score <= 1:
            return "完全陌生"
        elif score <= 3:
            return "陌生人"
        elif score <= 5:
            return "普通朋友"
        elif score <= 7:
            return "好朋友"
        elif score <= 9:
            return "亲密朋友"
        else:
            return "知己"

    relationship_display = f"{relationship_score} - {get_relationship_description(relationship_score)}" if relationship_score != "-" else "-"

    return {
        "name": log_path.name,
        "modified": modified,
        "turns": turns,
        "relationship_score": relationship_display,
        "last_user_text": _preview_text(last_user_text),
    }


def _list_chat_logs() -> list[Path]:
    CHAT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(
        [p for p in CHAT_LOG_DIR.glob("chat_*.log") if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


class ChatSessionLogger:
    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _append_line(self, text: str) -> None:
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(text.rstrip("\n") + "\n")

    def write_event(self, label: str, message: str = "") -> None:
        prefix = f"[{_now_display()}] {label}"
        self._append_line(prefix + message)

    def write_block(self, title: str, content: str) -> None:
        self._append_line(f"[{_now_display()}] {title}")
        for line in (content or "").splitlines() or [""]:
            self._append_line(f"    {line}")

    def log_session_start(self, resumed: bool) -> None:
        if resumed:
            self.write_event("SESSION_RESUME")
        else:
            self.write_event("SESSION_START")

    def log_user_message(self, user_text: str) -> None:
        self.write_event("你：", user_text)

    def log_turn_output(self, formatted_output: str, out: "TurnOutput", state: "GameState") -> None:
        self.write_block("系统输出：", formatted_output)
        turn_payload = {
            "talk_score": out.talk_score,
            "relationship_score": out.relationship_score,
            "cumulative_net_points": out.cumulative_net_points,
            "corresponding_reply": out.corresponding_reply,
            "sample_utterance": out.sample_utterance,
            "sample_score": out.sample_score,
            "sample_score_reason": out.sample_score_reason,
            "exit_triggered": out.exit_triggered,
            "forced_downgrade_count": out.forced_downgrade_count,
        }
        self.write_event("TURN_JSON: ", json.dumps(turn_payload, ensure_ascii=False))
        self.write_event("STATE_JSON: ", json.dumps(_state_to_dict(state), ensure_ascii=False))

    def log_summary(self, summary: dict[str, Any]) -> None:
        self.write_event("SUMMARY_JSON: ", json.dumps(summary, ensure_ascii=False))


def _generate_ai_suggestions_summary(log_path: Path) -> None:
    ai_suggestions_dir = PROJECT_DIR / "AI建议"
    ai_suggestions_dir.mkdir(parents=True, exist_ok=True)
    summary_file = ai_suggestions_dir / f"汇总_{log_path.stem}.txt"
    unified_file = ai_suggestions_dir / "汇总_所有会话建议.txt"

    state = _load_state_from_log(log_path)
    ai_role = state.ai_role or ""
    user_goal = state.user_goal or ""

    suggestions = []
    dialogue = []
    try:
        with log_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if "] 你：" in line:
                    user_text = line.split("你：", 1)[1].strip()
                    dialogue.append(("你", user_text))
                payload = _extract_json_payload(line, "TURN_JSON: ")
                if payload is not None:
                    corresponding = payload.get("corresponding_reply", "")
                    sample_utterance = payload.get("sample_utterance", "")
                    sample_score = payload.get("sample_score", "")
                    sample_score_reason = payload.get("sample_score_reason", "")

                    if corresponding:
                        dialogue.append(("AI", corresponding))

                    if sample_utterance or sample_score_reason:
                        suggestions.append(
                            {
                                "corresponding_reply": corresponding,
                                "sample_utterance": sample_utterance,
                                "sample_score": sample_score,
                                "sample_score_reason": sample_score_reason,
                            }
                        )
    except Exception:
        pass

    # 构建对话总结与口才评估
    summary_text = []
    summary_text.append(f"======== 对话总结 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ========")
    summary_text.append(f"AI角色：{ai_role}")
    summary_text.append(f"用户目标：{user_goal}")
    summary_text.append(f"会话轮次：{state.turns}")
    summary_text.append(f"最终关系分：{state.relationship_score}")
    summary_text.append(f"累计净积分：{state.cumulative_net_points}")
    summary_text.append("")
    summary_text.append("【对话上下文】")
    for speaker, text in dialogue:
        summary_text.append(f"{speaker}：{text}")

    # 口才能力评价（简单规则）
    ability_score = state.cumulative_net_points
    if ability_score >= 20 and state.relationship_score >= 5:
        ability = "表现优异：善于引导、把握场面、情感共振强。"
    elif ability_score >= 10:
        ability = "表现良好：交流流畅，能适度推动关系发展。"
    elif ability_score >= 0:
        ability = "表现一般：有基础表达，需更多情绪管理与清晰结构。"
    else:
        ability = "表现待提升：需要更强的倾听、共情与问题封闭能力。"

    summary_text.append("")
    summary_text.append("【口才能力评价】")
    summary_text.append(ability)
    summary_text.append("")
    summary_text.append("【优化建议】")
    summary_text.append("1. 保持逻辑线：先总结再引出问题，再给选项。")
    summary_text.append("2. 多用开放问题+复述对方要点，降低冲突。")
    summary_text.append("3. 调整语速语调（程序化反馈时可写‘慢/快’）。")
    summary_text.append("4. 视场景适当使用幽默、赞美、过渡语。")

    if suggestions:
        summary_text.append("")
        summary_text.append("【AI推荐话术】")
        for idx, s in enumerate(suggestions, start=1):
            summary_text.append(f"{idx}. 推荐回答：{s['sample_utterance']}")
            summary_text.append(f"   参考回复：{s['corresponding_reply']}")

    report_filename_goal = "_".join([c for c in (user_goal or "目标") if c.isalnum() or c == "_"])
    if not report_filename_goal:
        report_filename_goal = "目标"
    report_file = ai_suggestions_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{report_filename_goal}.txt"

    with report_file.open("w", encoding="utf-8") as fh:
        fh.write("\n".join(summary_text))

    with summary_file.open("w", encoding="utf-8") as fh:
        fh.write(f"AI建议汇总 - {log_path.name}\n")
        fh.write(f"AI角色：{ai_role}\n")
        fh.write(f"用户目标：{user_goal}\n\n")
        fh.write("对话上下文：\n")
        for speaker, text in dialogue:
            fh.write(f"{speaker}：{text}\n")
        fh.write("\n建议清单：\n")
        for idx, s in enumerate(suggestions, start=1):
            fh.write(f"{idx}. 推荐回答：{s['sample_utterance']}\n")
            fh.write(f"   参考回复：{s['corresponding_reply']}\n\n")

    with unified_file.open("a", encoding="utf-8") as fh:
        fh.write("=" * 78 + "\n")
        fh.write(f"会话日志：{log_path.name}\n")
        fh.write(f"AI角色：{ai_role}\n")
        fh.write(f"用户目标：{user_goal}\n")
        fh.write("对话上下文：\n")
        for speaker, text in dialogue:
            fh.write(f"{speaker}：{text}\n")
        fh.write("\n建议清单：\n")
        for idx, s in enumerate(suggestions, start=1):
            fh.write(f"{idx}. 推荐回答：{s['sample_utterance']}\n")
            fh.write(f"   参考回复：{s['corresponding_reply']}\n\n")
        fh.write("\n")

    print(f"\nAI建议汇总已保存到：{summary_file}")
    print(f"AI建议同时已附加到：{unified_file}")
    print(f"本次会话总结已保存到：{report_file}")
    print("\n".join(summary_text))


def _macro_analysis_for_roleplay(dialogue_history: list[tuple[str, str]], ai1_role: str, ai2_role: str, user_goal: str) -> None:
    print("\n=== 剧本宏观分析 ===")
    if dialogue_history:
        print(f"当前角色：{ai1_role} vs {ai2_role}")
        print(f"目标：{user_goal}")
        print("已完成对话轮次：", len(dialogue_history) // 2)
        print("最近对话片段：")
        for speaker, text in dialogue_history[-4:]:
            print(f"  {speaker}：{text}")
    else:
        print("尚无对话内容，先运行几轮剧本对话再分析。")

    print("\n宏观达成目标建议：")
    print("1. 明确目标和角色立场：在每轮对话中保持角色目标清晰，避免偏离故事主线。")
    print("2. 利用故事脉络引导情节：在每次自动对话前加入‘发展脉络’，让角色之间的互动循序渐进。")
    print("3. 关注节奏与冲突：若目标是推动关系，可先降低对抗；若目标是制造冲突，可逐步升级立场。")
    print("4. 结合情感线与动机线：在关键节点给出内心动机或转折提示，让角色反应更自然。\n")


def _auto_ai_vs_ai() -> None:
    from social_sim import GameState, SocialSimEngine  # type: ignore[reportMissingImports]

    print("\n=== 角色剧本编写模式 ===")
    user_goal = input(f"{ANSI_LIGHT_GREEN}请输入目标：{ANSI_RESET}").strip() or "目标"
    ai1_role = input(f"{ANSI_LIGHT_GREEN}请输入AI1角色描述：{ANSI_RESET}").strip() or "AI角色1"
    ai2_role = input(f"{ANSI_LIGHT_GREEN}请输入AI2角色描述：{ANSI_RESET}").strip() or "AI角色2"

    # 双向关系分：AI1看AI2、AI2看AI1
    default_a2b, reason_a2b = _auto_initial_relationship_score(ai1_role, user_goal)
    default_b2a, reason_b2a = _auto_initial_relationship_score(ai2_role, user_goal)

    raw_a2b = input(
        f"{ANSI_LIGHT_GREEN}请输入AI1({ai1_role})对AI2({ai2_role})的关系分（0-10，默认{default_a2b}，理由：{reason_a2b}）：{ANSI_RESET}"
    ).strip()
    try:
        a2b_score = min(max(int(raw_a2b), 0), 10) if raw_a2b else default_a2b
    except ValueError:
        a2b_score = default_a2b

    raw_b2a = input(
        f"{ANSI_LIGHT_GREEN}请输入AI2({ai2_role})对AI1({ai1_role})的关系分（0-10，默认{default_b2a}，理由：{reason_b2a}）：{ANSI_RESET}"
    ).strip()
    try:
        b2a_score = min(max(int(raw_b2a), 0), 10) if raw_b2a else default_b2a
    except ValueError:
        b2a_score = default_b2a

    max_turns = 60
    # 移除轮数输入，直接无限循环直到用户输入空格停止

    # 开始前输出AI双方立场与关系
    stance_a = _relationship_description(a2b_score)
    stance_b = _relationship_description(b2a_score)
    summary_stance = f"AI1({ai1_role}) 对 AI2({ai2_role}) 的视角：{stance_a}（{a2b_score}），AI2 对 AI1 的视角：{stance_b}（{b2a_score}）。"

    print(f"准备开始：{ai1_role} <--> {ai2_role}，目标：{user_goal}，无限轮对话（每轮各说一句，按空格停止）。\n")
    print("初始关系分（双向）：")
    print(f"  AI1看AI2：{a2b_score}，{stance_a}")
    print(f"  AI2看AI1：{b2a_score}，{stance_b}")
    print(f"一句话立场概述：{summary_stance}\n")

    state1 = GameState(relationship_score=a2b_score, ai_role=ai1_role, user_goal=user_goal)
    state2 = GameState(relationship_score=b2a_score, ai_role=ai2_role, user_goal=user_goal)
    engine1 = SocialSimEngine(state=state1)
    engine2 = SocialSimEngine(state=state2)

    current_text = f"你好，我是{ai1_role}。我与{ai2_role}的关系是：{stance_a}，初始关系分{a2b_score}。目标：{user_goal}。"

    dialogue_history = [("AI1", current_text)]

    def _run_dialogue_round() -> tuple[str, int]:
        nonlocal current_text
        nonlocal round_idx

        round_idx += 1
        print(f"\n=== 第 {round_idx} 轮（每AI各发言1次） ===")

        ai2_input = (
            f"你当前身份是{ai2_role}，你的对话对象身份是{ai1_role}。"
            f"对方说：{current_text}。"
            f"请作为{ai2_role}回应，保持你的立场：{stance_b}。"
        )
        out_ai2 = engine2.step(ai2_input)
        ai2_text = out_ai2.corresponding_reply or "(无输出)"
        print(f"{ANSI_CYAN}AI2({ai2_role}) -> AI1({ai1_role})：{ai2_text}{ANSI_RESET}")
        dialogue_history.append(("AI2", ai2_text))

        ai1_input = (
            f"你当前身份是{ai1_role}，你的对话对象身份是{ai2_role}。"
            f"对方说：{ai2_text}。"
            f"请作为{ai1_role}回应，保持你的立场：{stance_a}。"
        )
        out_ai1 = engine1.step(ai1_input)
        ai1_text = out_ai1.corresponding_reply or "(无输出)"
        print(f"{ANSI_CYAN}AI1({ai1_role}) -> AI2({ai2_role})：{ai1_text}{ANSI_RESET}")
        dialogue_history.append(("AI1", ai1_text))

        print(f"  AI2 话分: {out_ai2.talk_score}，关系分: {out_ai2.relationship_score}，累计净积分: {out_ai2.cumulative_net_points}")
        print(f"  AI1 话分: {out_ai1.talk_score}，关系分: {out_ai1.relationship_score}，累计净积分: {out_ai1.cumulative_net_points}")

        avg_relationship = (out_ai1.relationship_score + out_ai2.relationship_score) / 2
        print(f"本轮关系合并评分（平均）：{avg_relationship:.1f}，AI1关系{out_ai1.relationship_score}，AI2关系{out_ai2.relationship_score}")
        current_text = ai1_text
        return current_text, round_idx

    round_idx = 0
    while True:
        print(f"\n=== 当前轮次：{round_idx}，空格停止，回车继续，输入 a/b/c 触发功能：a=写入故事脉络，b=自动对话，c=宏观分析 ===")
        control = input(f"{ANSI_LIGHT_GREEN}请输入指令（空格停止，回车继续，a/b/c）：{ANSI_RESET}").strip().lower()

        if control == " ":
            print("检测到空格输入，结束对话。")
            break

        if control == "a":
            story_outline = input(f"{ANSI_LIGHT_GREEN}请输入当前故事下一步发展的脉络：{ANSI_RESET}").strip()
            if story_outline:
                current_text = f"{current_text}\n故事脉络：{story_outline}"
                print("故事脉络已记录，将影响后续剧情发展。")
            else:
                print("未输入故事脉络，保持当前剧情不变。")
            continue

        if control == "b":
            while True:
                raw_rounds = input(f"{ANSI_LIGHT_GREEN}请输入自动对话轮数（1-10）：{ANSI_RESET}").strip()
                try:
                    auto_rounds = int(raw_rounds)
                    if 1 <= auto_rounds <= 10:
                        break
                except ValueError:
                    pass
                print("请输入 1 到 10 之间的数字。")

            for _ in range(auto_rounds):
                _run_dialogue_round()
            continue

        if control == "c":
            _macro_analysis_for_roleplay(dialogue_history, ai1_role, ai2_role, user_goal)
            continue

        _run_dialogue_round()

    print("\n自动对话完成。")

    # 保存AI对话记录到文件夹
    two_ai_dir = PROJECT_DIR / "两AI对话记录"
    two_ai_dir.mkdir(parents=True, exist_ok=True)
    safe_goal = "".join(c if c.isalnum() else "_" for c in (user_goal or "目标"))[:64] or "目标"
    filename = f"{safe_goal}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    file_path = two_ai_dir / filename

    with file_path.open('w', encoding='utf-8') as fh:
        fh.write(f"AI对话记录 - 目标：{user_goal}\n")
        fh.write(f"AI1角色：{ai1_role}，AI1初始关系：{a2b_score}（{stance_a}）\n")
        fh.write(f"AI2角色：{ai2_role}，AI2初始关系：{b2a_score}（{stance_b}）\n")
        fh.write(f"总轮次（单向）：{round_idx}\n\n")
        fh.write("=== 对话内容 ===\n")
        for speaker, text in dialogue_history:
            fh.write(f"{speaker}：{text}\n")

        fh.write("\n=== 心理层次解析 ===\n")
        fh.write("1. 认知层：两位AI在对话中不断调整对方意图与自身目标，反映出双方对目标（{user_goal}）的聚焦或防御。\n")
        fh.write("2. 情绪层：通过关系分/话分判断情绪走向；高分表示积极认可，低分则倾向不信任或冲突。\n")
        fh.write("3. 动机层：AI1与AI2行为受角色模型牵引，交互体现目标驱动与自我保护。\n")
        fh.write("4. 互动层：中断提示可视为外部心理干预，促使观察者调整对话节奏和语境。\n")

    print(f"已保存两AI对话记录：{file_path}")


def _finalize_session(engine, logger, log_path: Path, trigger: str) -> None:
    s = engine.state.snapshot_for_summary()
    print("【综合评析】\n")
    def get_relationship_description(score: int) -> str:
        if score <= 1:
            return "完全陌生"
        elif score <= 3:
            return "陌生人"
        elif score <= 5:
            return "普通朋友"
        elif score <= 7:
            return "好朋友"
        elif score <= 9:
            return "亲密朋友"
        else:
            return "知己"

    print(f"- 最终关系分：{s['relationship_score']} - {get_relationship_description(s['relationship_score'])}")
    print(f"- 最终累计净积分：{s['cumulative_net_points']}")
    print(f"- 总轮次：{s['turns']}")
    print("\n【优化建议】\n")
    print("- 升温：多用“具体共情 + 轻度自曝 + 可选提问”，少用纯短句。")
    print("- 止损：先承认感受/边界，再给台阶，不要硬解释。")
    print("- 避免：辱骂、人身攻击、持续敷衍或强行重复夸赞。")

    logger.log_summary(s)
    logger.write_event("SESSION_END: ", trigger)

    _generate_ai_suggestions_summary(log_path)


def _select_chat_session() -> tuple["GameState", Path, bool]:
    from social_sim import GameState  # type: ignore[reportMissingImports]

    log_files = _list_chat_logs()

    print("\n聊天记录选择")
    print("-" * 58)
    if log_files:
        print("以下是已保存的聊天日志，可直接延续：\n")
        for idx, log_path in enumerate(log_files, start=1):
            info = _summarize_log(log_path)
            print(
                f"{idx}. {info['name']} | 最后更新：{info['modified']} | "
                f"轮次：{info['turns']} | 关系分：{info['relationship_score']} | 最近：{info['last_user_text']}"
            )
    else:
        print("目前还没有历史聊天记录。")

    print("0. 开启新聊天")

    while True:
        choice = input(f"{ANSI_LIGHT_GREEN}请选择要延续的日志编号（直接回车默认新聊天）：{ANSI_RESET}").strip()
        if not choice:
            choice = "0"

        if choice == "0":
            # 创建新对话，AI自动判定初始关系分（3-6）
            print("\n创建新对话：")
            ai_role = input(f"{ANSI_LIGHT_GREEN}请输入AI的角色描述（例如：一个温柔的女孩，喜欢聊天）：{ANSI_RESET}").strip()
            user_goal = input(f"{ANSI_LIGHT_GREEN}请输入你的目标（例如：学习编程，提高社交技能）：{ANSI_RESET}").strip()
            initial_score, reason = _auto_initial_relationship_score(ai_role, user_goal)
            print(f"自动判定初始关系分：{initial_score}（3-6）")
            print(f"判定理由：{reason}")

            state = GameState(relationship_score=initial_score, ai_role=ai_role, user_goal=user_goal)
            return state, _new_log_path(), False

        if choice.isdigit():
            selected = int(choice) - 1
            if 0 <= selected < len(log_files):
                return _load_state_from_log(log_files[selected]), log_files[selected], True

        print("输入无效，请按上面的编号重新选择。")


def run_cli() -> None:
    sys.path.insert(0, os.path.dirname(__file__))
    from social_sim import SocialSimEngine  # type: ignore[reportMissingImports]
    from social_sim.formatting import format_turn  # type: ignore[reportMissingImports]

    try:
        # Windows 控制台常见乱码：尽量强制 UTF-8 输出
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

    print("功能列表：")
    print("a. 角色剧本编写")
    print("b. 口才模拟")

    choice = input(f"{ANSI_LIGHT_GREEN}请选择功能（a/b，默认b）：{ANSI_RESET}").strip().lower()
    if not choice:
        choice = 'b'

    if choice == 'a':
        _auto_ai_vs_ai()
        return
    # else continue to b: normal chat

    initial_state, log_path, resumed = _select_chat_session()
    engine = SocialSimEngine(state=initial_state)
    logger = ChatSessionLogger(log_path)
    logger.log_session_start(resumed=resumed)

    print("\n" + "=" * 58)
    print("  真人社交模拟智能体")
    print("  输入“退出游戏”或直接回车结束并输出综合评析")
    print(f"  当前聊天日志：{log_path.name}")
    if resumed:
        def get_relationship_description(score: int) -> str:
            if score <= 1:
                return "完全陌生"
            elif score <= 3:
                return "陌生人"
            elif score <= 5:
                return "普通朋友"
            elif score <= 7:
                return "好朋友"
            elif score <= 9:
                return "亲密朋友"
            else:
                return "知己"
        print(
            f"  已恢复历史状态：关系分 {engine.state.relationship_score} - {get_relationship_description(engine.state.relationship_score)}，"
            f"累计净积分 {engine.state.cumulative_net_points}，总轮次 {engine.state.turns}"
        )
    else:
        print("  已开启新的聊天日志")
    print("=" * 58 + "\n")

    if resumed and engine.state.recent_user_texts:
        print("最近几轮用户输入已恢复：")
        for idx, text in enumerate(engine.state.recent_user_texts[-3:], start=1):
            print(f"  {idx}. {text}")
        print()

    while True:
        try:
            raw_user_text = input(f"{ANSI_LIGHT_GREEN}请输入您的对话或回复（回车结束对话）：{ANSI_RESET}")
        except (KeyboardInterrupt, EOFError):
            print("\n")
            logger.write_event("SESSION_END: ", "用户中断")
            break

        if raw_user_text == " ":
            print("检测到输入空格，结束当前会话并生成综合评析。")
            _finalize_session(engine, logger, log_path, "用户空格结束")
            break

        user_text = raw_user_text.strip()
        if not user_text:
            print("检测到直接回车，结束当前会话并生成综合评析。")
            _finalize_session(engine, logger, log_path, "用户回车结束")
            break

        logger.log_user_message(user_text)
        out = engine.step(user_text)
        formatted_output = format_turn(out)

        # 颜色分配：用户输入品红，AI输出青绿，AI具体回应亮黄
        print(f"\n{ANSI_MAGENTA}你：{user_text}{ANSI_RESET}")
        print(f"{ANSI_YELLOW}AI回复：{out.corresponding_reply}{ANSI_RESET}")
        print(f"{ANSI_CYAN}{formatted_output}{ANSI_RESET}\n")

        logger.log_turn_output(formatted_output, out, engine.state)

        if out.exit_triggered:
            _finalize_session(engine, logger, log_path, "用户主动退出")
            break


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.parse_args()
    _load_env()
    run_cli()
