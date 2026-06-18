import datetime
import json
import os
import requests
from flask import Flask, jsonify, request
from openai import OpenAI

app = Flask(__name__)

DB_FILE = "user_teams.json"

# Render 환경 변수(OPEN_API_KEY) 연동
OPENAI_API_KEY = os.environ.get("OPEN_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)


# -------------------------------------------------------------
# 💾 [데이터베이스 연동] JSON 파일 읽기/쓰기 함수
# -------------------------------------------------------------
def load_data():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_data(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


# -------------------------------------------------------------
# ⚾ [신규 크롤링 엔진] 네이버 스포츠 실시간 API 타격 함수 (경기 조회)
# -------------------------------------------------------------
def get_my_kbo_game(registered_team):
    """네이버 스포츠의 고성능 내부 데이터 API를 호출하여 오늘 경기 일정을 정확하게 가져옵니다."""
    kst_now = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
    today_str = kst_now.strftime("%Y-%m-%d")  # 예: '2026-06-18'

    # 💡 네이버 스포츠 실시간 스케줄 API 데이터 주소
    url = f"https://api-gw.sports.naver.com/schedule/games?gameDateTime={today_str}&category=kbo"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }

    try:
        response = requests.get(url, headers=headers, timeout=7)
        if response.status_code != 200:
            return "경기 일정을 불러올 수 없습니다. (포털 서버 응답 차단)"

        data = response.json()
        games = data.get("result", {}).get("games", [])

        if not games:
            return f"📅 [{today_str}] 오늘 예정된 KBO 경기가 없습니다. (휴식일)"

        search_team = registered_team.replace(" ", "").strip()

        for game in games:
            team_left_name = game.get("awayTeamName", "").replace(" ", "").strip()  # 원정팀
            team_right_name = game.get("homeTeamName", "").replace(" ", "").strip()  # 홈팀

            # 유저 팀이 대진표에 있는지 매칭 검사
            if (search_team in team_left_name) or (search_team in team_right_name):
                display_left = game.get("awayTeamName", "").strip()
                display_right = game.get("homeTeamName", "").strip()

                # 경기 시간 추출 및 정제 (예: "2026-06-18T18:30:00" -> "18:30")
                game_date_time = game.get("gameDateTime", "")
                game_time = game_date_time.split("T")[1][:5] if "T" in game_date_time else "18:30"

                # 선발 투수 정보 추출
                pitcher_left = game.get("awayPitcherName", "미정").strip()
                pitcher_right = game.get("homePitcherName", "미정").strip()

                if not pitcher_left: pitcher_left = "미정"
                if not pitcher_right: pitcher_right = "미정"

                result_text = f"⭐ 내가 등록한 팀 [{registered_team}] 경기 정보\n\n"
                result_text += f"📅 날짜: {today_str}\n"
                result_text += f"⏰ 시간: {game_time}\n"
                result_text += f"⚾ {display_left} ({pitcher_left}) vs {display_right} ({pitcher_right})\n\n"
                result_text += "※ 네이버 스포츠 실시간 API 연동 완료"
                return result_text

        return f"📅 오늘 [{registered_team}]의 경기 일정은 없습니다. (내 팀 휴식일)"

    except requests.exceptions.Timeout:
        return "⚠️ 포털 서버 연결 대기 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요!"
    except Exception as e:
        return f"경기 정보를 처리하는 중 에러가 발생했습니다: {str(e)}"


# -------------------------------------------------------------
# [스킬 1] 응원 팀 등록 주소 (/register-team)
# -------------------------------------------------------------
@app.route("/register-team", methods=["POST"])
def register_team():
    req = request.get_json()

    try:
        user_id = req["userRequest"]["user"]["id"]
        selected_team = req["action"]["clientExtra"]["team"]
    except (KeyError, TypeError) as e:
        return jsonify({"version": "2.0", "template": {"outputs": [{"simpleText": {"text": f"⚠️ 팀 등록 실패 (데이터 추출 오류)\n원인: {str(e)}"}}]} })

    user_data = load_data()
    user_data[user_id] = selected_team
    save_data(user_data)

    response_body = {
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": f"🎉 {selected_team} 등록이 완료되었습니다!\n앞으로 {selected_team}의 경기 정보와 실시간 순위를 알려드릴게요."}}]
        },
    }
    return jsonify(response_body)


# -------------------------------------------------------------
# [스킬 2] 오늘 경기 조회 주소 (/show-match)
# -------------------------------------------------------------
@app.route("/show-match", methods=["POST"])
def show_match():
    req = request.get_json()
    user_id = req["userRequest"]["user"]["id"]

    user_data = load_data()
    my_team = user_data.get(user_id)

    if not my_team:
        return jsonify({"version": "2.0", "template": {"outputs": [{"simpleText": {"text": "아직 응원 팀이 등록되지 않았어요! 😅\n'팀 등록'을 먼저 진행해 주세요."}}]}})

    match_text = get_my_kbo_game(my_team)
    return jsonify({"version": "2.0", "template": {"outputs": [{"simpleText": {"text": match_text}}]}})


# -------------------------------------------------------------
# 🤖 [스킬 3] GPT 연동 팀 전망 분석 주소 (/show-forecast)
# -------------------------------------------------------------
@app.route("/show-forecast", methods=["POST"])
def show_forecast():
    req = request.get_json()
    user_id = req["userRequest"]["user"]["id"]

    user_data = load_data()
    my_team = user_data.get(user_id)

    if not my_team:
        return jsonify({"version": "2.0", "template": {"outputs": [{"simpleText": {"text": "아직 응원 팀이 등록되지 않았어요! 😅\n'팀 등록'을 먼저 진행해 주세요."}}]}})

    try:
        prompt = f"너는 대한민국 최고의 프로야구 전문가야. 2026년 KBO 리그 시즌을 기준으로 [{my_team}] 팀의 전력, 핵심 선수, 그리고 이번 시즌 최종 성적 전망에 대해 카카오톡 챗봇에 어울리는 친근하고 유쾌한 말투로 300자 내외로 핵심만 요약해서 분석해줘."

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "너는 KBO 야구 전문가 챗봇이야. 야구 팬에게 말하듯이 이모티콘을 섞어가며 친근하게 답변해줘."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500,
            temperature=0.7
        )
        
        gpt_answer = response.choices[0].message.content.strip()
        forecast_text = f"🔮 GPT 야구 전문가가 분석한 [{my_team}]의 전망\n\n{gpt_answer}"

    except Exception as e:
        forecast_text = f"⚠️ GPT 서버와 연결하는 중 오류가 발생했습니다.\n오류 내용: {str(e)}"

    return jsonify({
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": forecast_text}}]
        }
    })


# -------------------------------------------------------------
# 🏆 [스킬 4] 네이버 스포츠 순위 API 타격 함수 (순위 조회)
# -------------------------------------------------------------
@app.route("/show-ranking", methods=["POST"])
def show_ranking():
    # 💡 개편 걱정 없는 네이버 스포츠 공식 순위 API 타격!
    url = "https://api-gw.sports.naver.com/custom/ranking/kbo"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=7)
        if response.status_code != 200:
            raise Exception("네이버 순위 서버 응답 실패")

        data = response.json()
        team_rankings = data.get("result", {}).get("teamRankings", [])

        ranking_list = ["🏆 2026 KBO 프로야구 실시간 순위", "-------------------------"]

        for team in team_rankings:
            rank = team.get("rank", "-")
            team_name = team.get("teamName", "미정")
            win_rate = team.get("winRegular", "-")  # 승률 데이터

            ranking_list.append(f"{rank}위: {team_name} (승률: {win_rate})")

        ranking_list.append("-------------------------")
        ranking_list.append("※ 네이버 스포츠 실시간 API 연동 성공")
        final_ranking_text = "\n".join(ranking_list)

    except Exception as e:
        final_ranking_text = f"⚠️ 실시간 순위를 가져오는 중 오류가 발생했습니다.\n오류 내용: 네이버 엔진 연결 불가 ({str(e)})"

    return jsonify({"version": "2.0", "template": {"outputs": [{"simpleText": {"text": final_ranking_text}}]}})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
