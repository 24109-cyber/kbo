import datetime
import json
import os
import base64
from flask import Flask, jsonify, request
from openai import OpenAI
from playwright.sync_api import sync_playwright

app = Flask(__name__)

DB_FILE = "user_teams.json"

# OpenAI 클라이언트 초기화 (Vision 기능을 쓰기 위해 필수)
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
# 📸 [혁신] 네이버 야구 화면을 진짜 캡처해서 GPT로 글자 읽기
# -------------------------------------------------------------
def get_match_by_screenshot(registered_team):
    if not client:
        return "⚠️ OpenAI API 키가 설정되지 않아 화면 분석을 할 수 없습니다."

    kst_now = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
    today_str = kst_now.strftime("%Y%m%d")
    today_display = kst_now.strftime("%Y-%m-%d")

    url = f"https://sports.news.naver.com/kbaseball/schedule/index?date={today_str}"
    screenshot_path = "/tmp/naver_kbo.png"

    try:
        # 1. 플레이라이트 브라우저를 열어 실제 네이버 화면 캡처하기
        with sync_playwright() as p:
            # Render 환경(리눅스) 대응을 위해 headless=True, 가벼운 크로미움 실행
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 1024})
            
            # 네이버 야구 일정 페이지로 이동 (완전히 로딩될 때까지 최대 10초 대기)
            page.goto(url, wait_until="networkidle", timeout=10000)
            page.wait_for_timeout(2000) # 리액트 동적 렌더링 안정화 대기
            
            # 야구 일정 스케줄러가 들어있는 구역만 정밀 캡처 (or 전체화면)
            container = page.query_selector("#_schedule_box") or page.query_selector(".content_schedule")
            if container:
                container.screenshot(path=screenshot_path)
            else:
                page.screenshot(path=screenshot_path, full_page=True)
                
            browser.close()

        # 2. 캡처한 이미지를 OpenAI API에 보낼 수 있게 Base64로 변환
        with open(screenshot_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')

        # 3. GPT-4o-mini의 Vision 기능을 이용해 이미지 안의 글자 판독 및 추출
        prompt = f"""
        첨부된 이미지는 오늘 대한민국 프로야구(KBO) 경기 일정표 스크린샷이야.
        이미지 안에서 사용자가 요청한 응원 팀인 [{registered_team}]의 경기 일정을 찾아서 양식에 맞춰 답변해줘.
        
        [주의사항]
        1. 만약 이미지 안에 [{registered_team}] 팀의 경기가 버젓이 있다면 절대 '일정이 없다'고 하지 말고, 눈에 보이는 팀명과 그 바로 옆에 적힌 선발 투수 이름을 그대로 읽어내야 해. (예: 롯데 이민석, 삼성 후라도, 한화 박준영 등)
        2. 오늘 날짜는 {today_display}이야.
        
        [답변 양식]
        ⭐ 내가 등록한 팀 [{registered_team}] 경기 정보

        📅 날짜: {today_display}
        ⏰ 시간: [이미지에 적힌 경기 시간, 예: 18:30]
        ⚾ [원정팀]([원정선발]) vs [홈팀]([홈선발])

        ※ 네이버 스포츠 화면 실시간 이미지 분석 완료
        """

        response = client.chat.completions.create(
            model="gpt-4o-mini",  # 이미지 분석이 가능한 강력하고 가벼운 모델
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
        return f"📸 화면 캡처 및 분석 중 오류가 발생했습니다.\n원인: {str(e)}"


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
            raise Exception("팀 정보 추출 실패")
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
        "template": {"outputs": [{"simpleText": {"text": f"🎉 {selected_team} 등록 완료!\n오늘 경기 조회를 해보세요."}}]}
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

    # 📸 새로 만든 이미지 분석 함수 호출!
    match_text = get_match_by_screenshot(my_team)
    
    return jsonify({
        "version": "2.0",
        "template": {"outputs": [{"simpleText": {"text": match_text}}]}
    })


# -------------------------------------------------------------
# [스킬 4] 네이버 스포츠 순위 크롤링 (/show-ranking)
# -------------------------------------------------------------
@app.route("/show-ranking", methods=["POST"])
def show_ranking():
    # 순위는 기존 텍스트 파싱을 유지하되, 필요 시 안정적으로 구동되게 보완
    url = "https://m.sports.naver.com/kbaseball/record/kbo?seasonCode=2026&tab=teamRank"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        import requests
        from bs4 import BeautifulSoup
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
