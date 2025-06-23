import json

current_response = []
with open("data", "r") as f:
    for raw_response in f:
        response = json.loads(raw_response)
        try:
            if "server_content" in response:
                parts = response["server_content"].get("model_turn", {}).get("parts", [])
                for part in parts:
                    if "text" in part:
                        current_response.append(part["text"])
        except Exception:
            pass

        try:
            turn_complete = response["server_content"]["turn_complete"]
            if turn_complete:
                if "".join(current_response).startswith("OK"):
                    print("初始化完成 ✅", style="green")
        except KeyError:
            pass
