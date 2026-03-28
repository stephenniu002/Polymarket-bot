import requests

# 把这里换成你刚刚配好的真实Token和纯数字ID
TOKEN = "7788042130:AAFJZo9LVP1fmjZjfn8wOvnCXBzCJMIU2Wg"
CHAT_ID = "7788042130"

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
payload = {"chat_id": CHAT_ID, "text": "🔔 恭喜！你的机器人配置彻底成功了！"}

response = requests.post(url, json=payload)
print("服务器返回:", response.text)
