import datetime
import json
import os
import requests
from flask import Flask, jsonify, request
from openai import OpenAI

app = Flask(__name__)

DB_FILE = "user_teams.json"

# Render에 등록한 'OPENAI_API_KEY'와 완벽하게 일치하도록 수정
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
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
# ⚾ [크롤링] 네이버 스포츠 KBO 오늘 경기 일정 조회 (선발투수 삭제 완료)
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
            return "경기 일정을 불러올 수 없습니다. (데이터 서버 응답 실패)"

        data = response.json()
        games = data.get("result", {}).get("games", [])

        if not games:
            return f"📅 [{today_str}] 오늘 예정된 KBO 경기가 없습니다. (내 팀 휴식일)"

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

                # 💡 [수정 포인트] 투수 정보 변수와 괄호 포맷을 완전히 지우고 누구 vs 누구만 남김!
                result_text = f"⭐ 내가 등록한 팀 [{registered_team}] 경기 정보\n\n"
                result_text += f"📅 날짜: {today_str}\n"
                result_text += f"⏰ 시간: {game_time}\n"
                result_text += f"⚾ {display_left} vs {display_right}\n\n"
                result_text += "※ 실시간 경기 데이터 반영"
                return result_text

        return f"📅 오늘 [{registered_team}]의 경기 일정은 없습니다. (내 팀 휴식일)"

    except Exception as e:
        return f"경기 정보 로딩 중 에러 발생: {str(e)}"


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
            raise Exception("팀 정보가 정상적으로 전달되지 않았습니다.")
            
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
        "template": {
            "outputs": [{
                "simpleText": {
                    "text": f"🎉 {selected_team} 등록 완료!\n실시간 순위와 매치 정보를 확인해보세요."
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
            "template": {"outputs": [{"simpleText": {"text": "아직 응원 팀이 등록되지 않았어요! 😅\n'팀 등록'을 먼저 진행해 주세요."}}]}
        })

    match_text = get_my_kbo_game(my_team)
    return jsonify({
        "version": "2.0",
        "template": {"outputs": [{"simpleText": {"text": match_text}}]}
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
            "template": {"outputs": [{"simpleText": {"text": "아직 응원 팀이 등록되지 않았어요! 😅"}}]}
        })

    if not client:
        return jsonify({
            "version": "2.0",
            "template": {"outputs": [{"simpleText": {"text": f"⚠️ OpenAI API 키 인식에 실패했습니다. (현재 로드된 키: {OPENAI_API_KEY})"}}]}
        })

    try:
        prompt = f"2026년 KBO 리그 시즌 기준으로 [{my_team}] 팀의 전력과 전망을 야구 전문가 말투로 200자 내외 요약해줘."
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "너는 KBO 야구 전문가 야구봇이야."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300,
            temperature=0.7
        )
        gpt_answer = response.choices[0].message.content.strip()
        forecast_text = f"🔮 GPT 전문가가 본 [{my_team}] 전망\n\n{gpt_answer}"
    except Exception as e:
        forecast_text = f"⚠️ GPT 분석 실패: {str(e)}"

    return jsonify({
        "version": "2.0",
        "template": {"outputs": [{"simpleText": {"text": forecast_text}}]}
    })


# -------------------------------------------------------------
# [스킬 4] 🏆 실시간 순위 조회 API
# -------------------------------------------------------------
@app.route("/show-ranking", methods=["POST"])
def show_ranking():
    req = request.get_json()
    try:
        user_id = req["userRequest"]["user"]["id"]
        selected_team = None
        if "params" in req.get("action", {}) and "team" in req["action"]["params"]:
            selected_team = req["action"]["params"]["team"]
        elif "clientExtra" in req.get("action", {}) and "team" in req["action"]["clientExtra"]:
            selected_team = req["action"]["clientExtra"]["team"]
            
        if not selected_team:
            user_data = load_data()
            selected_team = user_data.get(user_id)
    except Exception:
        selected_team = None

    url = "https://api-gw.sports.naver.com/kbaseball/category/record/team?seasonCode=2026"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://sports.news.naver.com",
        "Referer": "https://sports.news.naver.com/"
    }

    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code != 200:
            raise Exception(f"서버 응답 오류 (코드: {response.status_code})")

        data = response.json()
        regular_season = data.get("result", {}).get("regularSeason", {})
        team_list = regular_season.get("teamRecordList", [])

        if not team_list:
            raise Exception("순위 리스트 형식을 파싱할 수 없습니다.")

        ranking_list = ["🏆 2026 KBO 프로야구 실시간 순위", "-------------------------"]
        
        for idx, team in enumerate(team_list, start=1):
            rank = team.get("rank", idx)
            team_name = team.get("teamName", "-")
            
            if team_name != "-":
                if selected_team and (selected_team.replace(" ", "") in team_name.replace(" ", "")):
                    ranking_list.append(f"⭐ {rank}위: {team_name} (내 팀)")
                else:
                    ranking_list.append(f"{rank}위: {team_name}")

        ranking_list.append("-------------------------")
        ranking_list.append("※ 네이버 스포츠 실시간 데이터")
        final_ranking_text = "\n".join(ranking_list)

    except Exception as e:
        final_ranking_text = f"⚠️ 순위 조회 중 오류가 발생했습니다.\n원인: {str(e)}"

    return jsonify({
        "version": "2.0",
        "template": {"outputs": [{"simpleText": {"text": final_ranking_text}}]}
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
