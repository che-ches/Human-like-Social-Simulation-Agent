# 真人社交模拟智能体

通过**量化评分**模拟人际关系的“易坏难养”、信任累积与消耗的**非对称动态**。每轮对话都按固定格式输出：

- 话分（0~10）
- 关系分（0~10）
- 累计净积分（可正可负）
- AI 对应回应（按关系分范式）
- 学习参考：示例话术 + 示例评分 + 评分简述（**不计入计分**）

## 运行（CLI）

```bash
pip install -r requirements.txt
python main.py
```

输入 `退出游戏` 结束并输出综合评析与优化建议。

## 运行（Web）

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 核心代码位置

- `social_sim/engine.py`：计分、升级/降级、强制规则与状态更新
- `social_sim/formatting.py`：固定输出格式渲染
- `social_sim/judge.py`：对用户单次回复打“话分”（当前为离线启发式，可后续替换为 LLM 判分）
- `social_sim/response.py`：对应回应 + 示例话术生成

