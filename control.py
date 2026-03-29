from flask import Flask, request

app = Flask(name)

SECRET = "88888888"   # 你自己改一个


@app.route("/control", methods=["POST"])
def control():
    data = request.json

    # 安全校验
    if data.get("key") != SECRET:
        return {"msg": "unauthorized"}

    cmd = data.get("cmd")

    if cmd == "start":
        print("启动任务")
        return {"msg": "已启动"}

    elif cmd == "stop":
        print("停止任务")
        return {"msg": "已停止"}

    elif cmd == "status":
        return {"msg": "运行中"}

    return {"msg": "未知指令"}


app.run(host="0.0.0.0", port=3000)
