import datetime
import json
import os
import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request
from openai import OpenAI

app = Flask(__name__)

DB_FILE = "user_teams.json"

# OpenAI 클라이언트 안전하게 선언 (Render 환경변수 OPEN_API_KEY 사용)
OPENAI_API_KEY = os.environ.get("OPEN_API_KEY", "")
client = None
if OPENAI_API_KEY:
    # 💡 에러 방지를 위해 가장 기본적이고 안전한 형태로 선언합니다.
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
# ⚾ [크롤링] 네이버 스포츠 KBO 오늘 경기 일정 조회
# -------------------------------------------------------------
def get_my_kbo_game(registered_team):
    kst_now = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
    today_str = kst_now.strftime("%Y-%m-%d")

    url = f"https://api-gw.sports.naver.com/schedule/games?upperCategoryId=kbaseball&date={today_str}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=7)
        if response.status_code != 200:
            return "경기 일정을 불러올 수 없습니다. (포털 서버 API 응답 에러)"

        data = response.json()
        games = data.get("result", {}).get("games", [])

        if not games:
            return f"📅 [{today_str}] 오늘 예정된 KBO 경기가 없습니다. (휴식일)"

        search_team = registered_team.replace(" ", "").strip()

        for game in games:
            team_left_name = game.get("awayTeamName", "").replace(" ", "").strip()
            team_right_name = game.get("homeTeamName", "").replace(" ", "").strip()

            if (search_team in team_left_name) or (search_team in team_right_name):
                display_left = game.get("awayTeamName", "").strip()
                display_right = game.get("homeTeamName", "").strip()

                game_date_time = game.get("gameDateTime", "")
                game_time = (
                    game_date_time.split("T")[1][:5]
                    if "T" in game_date_time
                    else "18:30"
                )

                pitcher_left = game.get("awayPitcherName", "미정").strip()
                pitcher_right = game.get("homePitcherName", "미정").strip()

                result_text = f"⭐ 내가 등록한 팀 [{registered_team}] 경기 정보\n\n"
                result_text += f"📅 날짜: {today_str}\n"
                result_text += f"⏰ 시간: {game_time}\n"
                result_text += f"⚾ {display_left} ({pitcher_left}) vs {display_right} ({pitcher_right})\n\n"
                result_text += "※ 네이버 스포츠 실시간 API 연동 완료"
                return result_text

        return f"📅 오늘 [{registered_team}]의 경기 일정은 없습니다. (내 팀 휴식일)"

    except Exception as e:
        return f"경기 정보를 처리하는 중 에러가 발생했습니다: {str(e)}"


# -------------------------------------------------------------
# [스킬 1] 응원 팀 등록 (/register-team)
# -------------------------------------------------------------
@app.route("/register-team", methods=["POST"])
def register_team():
    req = request.get_json()
    try:
        user_id = req["userRequest"]["user"]["id"]
        # 블록 설정에 따라 다양한 경로로 들어올 수 있으므로 예외처리 강화
        selected_team = None
        if "clientExtra" in req.get("action", {}) and "team" in req["action"]["clientExtra"]:
            selected_team = req["action"]["clientExtra"]["team"]
        elif "params" in req.get("action", {}) and "team" in req["action"]["params"]:
            selected_team = req["action"]["params"]["team"]
            
        if not selected_team:
            raise Exception("선택된 팀 파라미터가 없습니다.")
            
    except Exception as e:
        return jsonify({
            "version": "2.0",
            "template": {
                "outputs": [{
                    "simpleText": {
                        "text": f"⚠️ 팀 등록 실패\n원인: {str(e)}"
                    }
                }]
            },
        })

    user_data = load_data()
    user_data[user_id] = selected_team
    save_data(user_data)

    return jsonify({
        "version": "2.0",
        "template": {
            "outputs": [{
                "simpleText": {
                    "text": f"🎉 {selected_team} 등록이 완료되었습니다!\n앞으로 {selected_team}의 경기 정보와 실시간 순위를 알려드릴게요."
                }
            }]
        },
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
            "template": {
                "outputs": [{
                    "simpleText": {
                        "text": "아직 응원 팀이 등록되지 않았어요! 😅\n'팀 등록'을 먼저 진행해 주세요."
                    }
                }]
            },
        })

    match_text = get_my_kbo_game(my_team)
    return jsonify({
        "version": "2.0",
        "template": {"outputs": [{"simpleText": {"text": match_text}}]},
    })


# -------------------------------------------------------------
# [스킬 3] GPT 팀 전망 분석 (/show-forecast)
# -------------------------------------------------------------
@app.route("/show-forecast", methods=["POST"])
def show_forecast():
    req = request.get_json()
    user_id = req["userRequest"]["user"]["id"]

    user_data = load_data()
    my_team = user_data.get(user_id)

    if not my_team:
        return jsonify({
            "version": "2.0",
            "template": {
                "outputs": [{
                    "simpleText": {
                        "text": "아직 응원 팀이 등록되지 않았어요! 😅\n'팀 등록'을 먼저 진행해 주세요."
                    }
                }]
            },
        })

    if not client:
        return jsonify({
            "version": "2.0",
            "template": {
                "outputs": [{
                    "simpleText": {
                        "text": "⚠️ OpenAI API 키가 설정되지 않았거나 서버 오류입니다."
                    }
                }]
            },
        })

    try:
        prompt = f"2026년 KBO 리그 시즌 기준으로 [{my_team}] 팀의 전력과 시즌 전망에 대해 친근한 야구 전문가 말투로 200자 내외 요약해줘."

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "너는 KBO 야구 전문가 챗봇이야. 친근하게 답변해줘."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=300,
            temperature=0.7,
        )

        gpt_answer = response.choices[0].message.content.strip()
        forecast_text = f"🔮 GPT 야구 전문가가 분석한 [{my_team}]의 전망\n\n{gpt_answer}"

    except Exception as e:
        forecast_text = f"⚠️ GPT 전망 분석 실패: {str(e)}"

    return jsonify({
        "version": "2.0",
        "template": {"outputs": [{"simpleText": {"text": forecast_text}}]},
    })


# -------------------------------------------------------------
# [스킬 4] 네이버 스포츠 순위 크롤링 및 파싱 (/show-ranking)
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

        # 네이버 리액트 동적 클래스 li 태그 전체 검색
        rows = soup.select("ol[class*='TableBody_list'] li")

        if not rows:
            raise Exception("순위 데이터 영역(HTML 구조)을 찾지 못했습니다.")

        ranking_list = ["🏆 2026 KBO 프로야구 실시간 순위", "-------------------------"]

        for row in rows:
            rank_tag = row.select_one("em[class*='TeamInfo_ranking']")
            team_tag = row.select_one("div[class*='TeamInfo_team_name']")
            
            # 💡 [핵심 보완] 특정 클래스 대신 wra(승률) blind 태그의 부모를 추적하여 파싱 에러 방지
            win_rate = "-"
            wra_blind = row.find("span", text="wra") or row.find("span", class_="blind", string="wra")
            if wra_blind:
                parent_div = wra_blind.find_parent("div")
                if parent_div:
                    win_rate = parent_div.get_text().replace("wra", "").strip()

            if rank_tag and team_tag:
                rank = rank_tag.get_text().replace("위", "").strip()
                team_name = team_tag.get_text().strip()
                ranking_list.append(f"{rank}위: {team_name} (승률: {win_rate})")

        ranking_list.append("-------------------------")
        ranking_list.append("※ 네이버 스포츠 실시간 크롤링 완료")
        final_ranking_text = "\n".join(ranking_list)

    except Exception as e:
        final_ranking_text = f"⚠️ 실시간 순위 데이터 파싱 실패\n원인: {str(e)}"

    return jsonify({
        "version": "2.0",
        "template": {"outputs": [{"simpleText": {"text": final_ranking_text}}]},
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
