async def main(args):
    import json

    data = args.get('data') if isinstance(args, dict) else None
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            data = {}
    if not isinstance(data, dict):
        data = {}

    # ==============================================
    # 万能兼容：自动找真实业务字段
    # ==============================================
    result = (
        data.get("resp")
        or data.get("output")
        or data.get("response")
        or data
    )

    BOOL_MAP = {True: "是", False: "否"}
    DEMAND_MAP = {"显性需求": "显性需求", "隐性需求": "隐性需求", "无需求": "无需求"}
    TRIGGER_MAP = {"自动触发": "自动触发", "主动询问": "主动询问", "不触发": "不触发"}

    return {
        "用户Query": result.get("query", ""),
        "是否有生图需求": BOOL_MAP.get(result.get("has_image_demand"), "否"),
        "需求类型": DEMAND_MAP.get(result.get("demand_type"), "无需求"),
        "场景分类": result.get("scene_category", "未知"),
        "推荐生图形态": result.get("recommended_image_type", "无"),
        "置信度": f"{result.get('confidence', 0)*100:.0f}%",
        "触发建议": TRIGGER_MAP.get(result.get("trigger_suggestion"), "不触发"),
        "判断依据": result.get("reason", "")
    }