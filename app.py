from flask import Flask, request, jsonify
import gspread
from oauth2client.service_account import ServiceAccountCredentials # type: ignore
import requests
from dotenv import load_dotenv
import os

# Khởi tạo Flask và load .env 
app = Flask(__name__)
@app.route("/")
def index():
    return "Chào bạn, Flask đã chạy thành công!"
load_dotenv()

# Biến môi trường
ZALO_ACCESS_TOKEN = os.getenv("ZALO_ACCESS_TOKEN")
ZALO_API_URL     = "https://openapi.zalo.me/v3.0/oa/message"
GOOGLE_SHEET_ID  = os.getenv("GOOGLE_SHEET_ID")

# Thiết lập credentials Google Sheets
scope = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]
creds  = ServiceAccountCredentials.from_json_keyfile_name("creds.json", scope)
client = gspread.authorize(creds)
sheet  = client.open_by_key(GOOGLE_SHEET_ID).sheet1

# Link mặc định nếu sheet chưa có URL
DEFAULT_FORMS = {
    "form_1": "https://drive.google.com/file/d/1nPd0Zs50fEzKLjJMEOUFjXPfwOxPWROf/uc?export=download",
    "form_2": "https://drive.google.com/file/d/1jveCG0pcRQt4vuFVOekUYwAz5jQ9C3vY/uc?export=download",
    "form_3": "https://drive.google.com/file/d/124zgnEeb0nU-DfQzcqh27MWtKS-WuF3D/uc?export=download",
}

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        return "Zalo Webhook xác thực thành công!", 200

    data  = request.json or {}
    event = data.get('event_name')

    # Xử lý sự kiện follow
    if event == "follow":
        user_id = data.get('user_id')
        if user_id:
            records = sheet.get_all_records()
            # Nếu chưa có trong sheet thì thêm mới
            if not any(str(r["user_id_zalo"]) == str(user_id) for r in records):
                sheet.append_row(["Chưa xác định", user_id, "", "", ""])
                send_zalo_message(user_id, "Cảm ơn bạn đã follow! Nhấn biểu mẫu để nhận tài liệu.")
        return jsonify({"message": "follow handled"}), 200

    # Xử lý khi user bấm chọn form
    elif event == "user_send_message":
        user_id   = data.get('sender', {}).get('id')
        form_type = data.get('form_type')

        # Kiểm tra đã follow chưa
        if not check_follow_status(user_id):
            send_zalo_message(user_id, "Vui lòng follow OA để nhận biểu mẫu!")
            return jsonify({"message": "not a follower"}), 403

        # Tìm link trong sheet
        col_map = {"form_1":"form_1_url","form_2":"form_2_url","form_3":"form_3_url"}
        col     = col_map.get(form_type)
        records = sheet.get_all_records()
        link    = None
        if col:
            link = next((r[col] for r in records if str(r["user_id_zalo"]) == str(user_id)), None)

        # Nếu sheet chưa có, dùng link mặc định
        if not link:
            link = DEFAULT_FORMS.get(form_type)

        # Gửi file PDF
        if link:
            send_zalo_file(user_id, link)
            return jsonify({"message": f"sent {form_type}"}), 200

        # Trường hợp không tìm được form
        send_zalo_message(user_id, "Hiện chưa có biểu mẫu, vui lòng thử lại sau.")
        return jsonify({"message": "form not found"}), 404

    # Unknown event
    return jsonify({"message": "unknown event"}), 400



def check_follow_status(user_id):
    """Kiểm tra xem user đã follow OA chưa."""
    if not user_id:
        return False
    resp = requests.get(
        f"https://openapi.zalo.me/v2.0/oa/getuser?user_id={user_id}",
        headers={"access_token": ZALO_ACCESS_TOKEN}
    )
    if resp.status_code == 200:
        return resp.json().get("data", {}).get("is_follower", 0) == 1
    return False


def send_zalo_file(user_id, file_url):
    """Gửi file PDF qua API Zalo OA."""
    payload = {
        "recipient": {"user_id": user_id},
        "message": {
            "attachment": {
                "type": "file",
                "payload": {"file_type":"pdf", "url": file_url}
            }
        }
    }
    requests.post(ZALO_API_URL, json=payload, headers={"access_token": ZALO_ACCESS_TOKEN})


def send_zalo_message(user_id, text):
    """Gửi tin nhắn text qua API Zalo OA."""
    payload = {
        "recipient": {"user_id": user_id},
        "message": {"text": text}
    }
    requests.post(ZALO_API_URL, json=payload, headers={"access_token": ZALO_ACCESS_TOKEN})


if __name__ == "__main__":
    # Chạy debug=True chỉ trong dev, production dùng gunicorn
    app.run(host="0.0.0.0", port=5000, debug=True)
