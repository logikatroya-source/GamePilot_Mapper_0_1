def normalize_profile(data):
    """Normalize current and legacy profile dictionaries into v2 shape."""
    if not isinstance(data, dict):
        raise ValueError("Профиль должен быть JSON-объектом")
    if "steps" in data:
        raw_steps = data.get("steps") or []
    elif data.get("point"):
        x, y = data["point"]
        raw_steps = [{"name": "Ресурс 1", "x": x, "y": y,
                      "clicks": data.get("clicks", 1), "wait": data.get("gather_wait", 5)}]
    else:
        raw_steps = []
    steps = []
    for index, item in enumerate(raw_steps):
        if not isinstance(item, dict) or "x" not in item or "y" not in item:
            raise ValueError(f"Некорректная точка сценария №{index + 1}")
        x, y = int(item["x"]), int(item["y"])
        if x < 0 or y < 0:
            raise ValueError(f"Координаты точки №{index + 1} не могут быть отрицательными")
        steps.append({
            "name": str(item.get("name") or f"Ресурс {index + 1}"),
            "x": x, "y": y,
            "clicks": min(5, max(1, int(item.get("clicks", data.get("clicks", 1))))),
            "wait": min(300.0, max(0.1, float(item.get("wait", data.get("gather_wait", 5)))))
        })
    return {
        "steps": steps,
        "repeats": min(10000, max(1, int(data.get("repeats", 10)))),
        "clicks": min(5, max(1, int(data.get("clicks", 1)))),
        "gather_wait": min(300.0, max(0.1, float(data.get("gather_wait", 5)))),
        "interval": min(300.0, max(0.0, float(data.get("interval", 1))))
    }

