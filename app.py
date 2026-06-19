import datetime
import json
import os
import base64
import requests
from flask import Flask, jsonify, request
from openai import OpenAI

app = Flask(__name__)

DB_FILE = "user_teams.json"

# OpenAI 클라이언트 초기화
OPENAI_API_KEY = os.environ.get("OPEN_API_KEY", "")
client = None
if OPENAI_API_KEY:
    client = OpenAI(api_key=OPENAI_API_KEY)


def load_data():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except:
                return {}
    return {}


def save_data(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


# -------------------------------------------------------------
# 📸 [우회] 외부 캡처 서비스를 이용해 네이버 야구 화면을 가져온 뒤 GPT 분석
# -------------------------------------------------------------
def get_match_by_screenshot_api(registered_team):
    if not client:
        return "⚠️ OpenAI API 키가 설정되지 않아 화면 분석을 할 수 없습니다."

    kst_now = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
    today_str = kst_now.strftime("%Y%m%d")
    today_display = kst_now.strftime("%Y-%m-%d")

    # 네이버 KBO 프로야구 일정 URL
    naver_url = f"https://sports.news.naver.com/kbaseball/schedule/index?date={today_str}"
    
    # 💡 무료 글로벌 웹 스크린샷 렌더링 API 사용 (서버에 브라우저를 깔지 않는 방식)
    # thum.io 서비스는 특정 URL을 브라우저로 열어 이미지로 반환해줍니다.
    capture_api_url = f"https://image.thum.io/get/width/1280/crop/800/{naver_url}"

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        # 외부 API를 호출하여 이미지 바이너리 획득
        img_response = requests.get(capture_api_url, headers=headers, timeout=15)
        if img_response.status_code != 200:
            return "⚠️ 네이버 화면을 이미지로 변환하는 데 실패했습니다. (외부 API 지연)"

        # 이미지를 Base64 인코딩
        base64_image = base64.b64encode(img_response.content).decode('utf-8')

        # GPT-4o-mini Vision 분석 요청
        prompt = f"""
        첨부된 이미지는 오늘 KBO 프로야구 경기 일정표 화면이야.
        이미지에서 사용자가 지정한 팀인 [{registered_team}]의 경기 일정을 찾아서 출력 양식에 맞게 텍스트로만 요약해줘.
        
        [지시사항]
        1. 오늘 날짜는 {today_display}이야.
        2. 이미지 안에 [{registered_team}]의 경기가 적혀있다면 팀 이름 바로 옆에 붙어있는 선발 투수 이름(예: 이민석, 후라도 등)을 찾아서 괄호 안에 매칭해줘야 해.
        3. 만약 텍스트 판독이 어렵거나 누락되었다면, 이미지에 보이는 텍스트 흐름을 유추해서 최대한 완성해줘.

        [출력 양식]
        ⭐ 내가 등록한 팀 [{registered_team}] 경기 정보

        📅 날짜: {today_display}
        ⏰ 시간: [경기 시간, 예: 18:30]
        ⚾ [원정팀]([원정선발]) vs [홈팀]([홈선발])

        ※ 실시간 네이버 야구 전광판 비전 분석 결과입니다.
        """

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=400
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        return f"⚠️ 이미지 기반 야구 전광판 분석 중 에러가 발생했습니다.\n원인: {str(e)}"


# -------------------------------------------------------------
# [스킬 1] 응원 팀 등록 (/register-team)
# -------------------------------------------------------------
@app.route("/register-team", methods=["POST"])
def register_team():
    req = request.get_json()
    try:
        user_id = req["userRequest"]["user"]["id"]
        selected_team = None
        if "clientExtra" in req.get("action", {}) and "team" in req["action"]["clientExtra"]:
            selected_team = req["action"]["clientExtra"]["team"]
        elif "params" in req.get("action", {}) and "team" in req["action"]["params"]:
            selected_team = req["action"]["params"]["team"]
            
        if not selected_team:
            raise Exception("팀 정보 누락")
    except Exception as e:
        return jsonify({
            "version": "2.0",
            "template": {"outputs": [{"simpleText": {"text": f"⚠️ 팀 등록 실패: {str(e)}"}}]}
        })

    user_data = load_data()
    user_data[user_id] = selected_team
    save_data(user_data)

    return jsonify({
        "version": "2.0",
        "template": {"outputs": [{"simpleText": {"text": f"🎉 {selected_team} 등록 완료!\n'경기'를 입력해 스크린샷 분석 데이터를 받아보세요."}}]}
    })


# -------------------------------------------------------------
# [스킬 2] 오늘 경기 조회 (/show-match)
# -------------------------------------------------------------
@app.route("/show-match", methods=["POST"])
def show_match():
    req = request.get_json()
    user_id = req["userRequest"]["user"]["id"]

    user_data = load_data()
    my_team = user_data.get(user_id)

    if not my_team:
        return jsonify({
            "version": "2.0",
            "template": {"outputs": [{"simpleText": {"text": "아직 응원 팀이 등록되지 않았어요! 😅"}}]}
        })

    # 📸 외부 이미지 캡처 연동형 함수 호출
    match_text = get_match_by_screenshot_api(my_team)
    
    return jsonify({
        "version": "2.0",
        "template": {"outputs": [{"simpleText": {"text": match_text}}]}
    })


# -------------------------------------------------------------
# [스킬 4] 네이버 스포츠 순위 크롤링 (/show-ranking)
# -------------------------------------------------------------
@app.route("/show-ranking", methods=["POST"])
def show_ranking():
    url = "https://m.sports.naver.com/kbaseball/record/kbo?seasonCode=2026&tab=teamRank"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=7)
        soup = BeautifulSoup(response.text, "html.parser")
        rows = soup.select("ol[class*='TableBody_list'] li")

        ranking_list = ["🏆 2026 KBO 프로야구 실시간 순위", "-------------------------"]
        for row in rows:
            rank_tag = row.select_one("em[class*='TeamInfo_ranking']")
            team_tag = row.select_one("div[class*='TeamInfo_team_name']")
            cells = row.select("div[class*='TableRow_cell_text']")
            win_rate = cells[4].get_text().strip() if len(cells) >= 5 else "-"

            if rank_tag and team_tag:
                ranking_list.append(f"{rank_tag.get_text().strip()}위: {team_tag.get_text().strip()} (승률: {win_rate})")
        ranking_list.append("-------------------------")
        final_text = "\n".join(ranking_list)
    except Exception as e:
        final_text = f"⚠️ 순위 가져오기 실패: {str(e)}"

    return jsonify({
        "version": "2.0",
        "template": {"outputs": [{"simpleText": {"text": final_text}}]}
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
