import datetime
import json
import os
import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request

app = Flask(__name__)

DB_FILE = "user_teams.json"


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
# ⚾ [크롤링 엔진] 다음 스포츠 내부 진짜 API를 타격하는 강력한 함수
# -------------------------------------------------------------
def get_my_kbo_game(registered_team):
    """다음 스포츠의 실시간 내부 데이터 서버(JSON API)를 직접 호출하여 100% 매칭"""
    # 해외 서버 시간대 보정 (한국 시간 KST 세팅)
    kst_now = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
    today_str = kst_now.strftime("%Y-%m-%d")  # 예: '2026-06-18'

    # 💡 웹페이지 대신 다음 스포츠가 내부적으로 데이터를 몰래 불러오는 진짜 실시간 API 주소!
    url = f"https://sports.daum.net/prx/hermes/api/schedule/kbo?date={today_str}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=7)
        if response.status_code != 200:
            return "경기 일정을 불러올 수 없습니다. (포털 서버 API 응답 에러)"

        # HTML 파싱 대신 훨씬 정확하고 빠른 JSON 데이터 통째로 읽기
        data = response.json()
        games = data.get("scheduleList", [])

        if not games:
            return f"📅 [{today_str}] 오늘 예정된 KBO 경기가 없습니다. (휴식일)"

        # 사용자가 등록한 풀네임(예: "KT 위즈")에서 공백 빼고 앞 2글자(예: "KT") 추출
        short_team_name = registered_team.replace(" ", "")[:2]

        for game in games:
            team_left_name = game.get("teamName1", "").strip()  # 원정팀
            team_right_name = game.get("teamName2", "").strip()  # 홈팀

            # 내가 등록한 팀 이름 조각이 대진표에 있는지 매칭 검사
            if (short_team_name in team_left_name) or (
                short_team_name in team_right_name
            ):
                # 경기 시간 추출 및 가공 (예: "1830" -> "18:30")
                raw_time = game.get("startTime", "1830")
                game_time = (
                    f"{raw_time[:2]}:{raw_time[2:4]}"
                    if len(raw_time) >= 4
                    else "18:30"
                )

                # 선발 투수 추출 (없으면 미정)
                pitcher_left = game.get("pitcherName1", "미정").strip()
                pitcher_right = game.get("pitcherName2", "미정").strip()

                if not pitcher_left:
                    pitcher_left = "미정"
                if not pitcher_right:
                    pitcher_right = "미정"

                result_text = f"⭐ 내가 등록한 팀 [{registered_team}] 경기 정보\n\n"
                result_text += f"📅 날짜: {today_str}\n"
                result_text += f"⏰ 시간: {game_time}\n"
                result_text += f"⚾ {team_left_name} ({pitcher_left}) vs {team_right_name} ({pitcher_right})\n\n"
                result_text += "※ 다음 스포츠 실시간 API 연동 성공"
                return result_text

        return f"📅 오늘 [{registered_team}]의 경기 일정은 없습니다. (내 팀 휴식일)"

    except requests.exceptions.Timeout:
        return "⚠️ 다음 스포츠 서버 연결 대기 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요!"
    except Exception as e:
        return f"경기 정보를 처리하는 중 에러가 발생했습니다: {str(e)}"


# -------------------------------------------------------------
# [스킬 1] 응원 팀 등록 주소 (/register-team) -> 🔥 파라미터 파싱 구조 전면 수정!
# -------------------------------------------------------------
@app.route("/register-team", methods=["POST"])
def register_team():
    req = request.get_json()

    try:
        user_id = req["userRequest"]["user"]["id"]
        # 💡 [긴급 수정] clientExtra 대신 캡처 화면의 '추가 정보(params)' 규격으로 정확히 연결!
        selected_team = req["action"]["params"]["team"]
    except (KeyError, TypeError):
        return jsonify(
            {
                "version": "2.0",
                "template": {
                    "outputs": [
                        {
                            "simpleText": {
                                "text": "⚠️ 팀 등록 중 에러가 발생했습니다. 카카오톡 봇 설정을 확인해 주세요."
                            }
                        }
                    ]
                },
            }
        )

    user_data = load_data()
    user_data[user_id] = selected_team
    save_data(user_data)

    response_body = {
        "version": "2.0",
        "template": {
            "outputs": [
                {
                    "simpleText": {
                        "text": f"🎉 {selected_team} 등록이 완료되었습니다!\n앞으로 {selected_team}의 경기 정보와 실시간 순위를 알려드릴게요."
                    }
                }
            ]
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
        return jsonify(
            {
                "version": "2.0",
                "template": {
                    "outputs": [
                        {
                            "simpleText": {
                                "text": "아직 응원 팀이 등록되지 않았어요! 😅\n'팀 등록'을 먼저 진행해 주세요."
                            }
                        }
                    ]
                },
            }
        )

    # 수정된 고성능 API 크롤링 함수 호출
    match_text = get_my_kbo_game(my_team)

    return jsonify(
        {
            "version": "2.0",
            "template": {"outputs": [{"simpleText": {"text": match_text}}]},
        }
    )


# -------------------------------------------------------------
# [스킬 3] 다음 스포츠 HTML 맞춤형 실시간 순위 (/show-ranking)
# -------------------------------------------------------------
@app.route("/show-ranking", methods=["POST"])
def show_ranking():
    try:
        url = "https://sports.daum.net/record/KBO"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=7)
        soup = BeautifulSoup(response.text, "html.parser")

        table_rows = soup.select(".record_kbo .tbl_record tbody tr")
        ranking_list = [
            "🏆 2026 KBO 프로야구 실시간 순위",
            "-------------------------",
        ]

        count = 0
        for row in table_rows:
            rank_tag = row.select_one(".td_rank")
            team_tag = row.select_one(".txt_name")
            win_rate_tag = row.select_one('td[data-field="rank"]')

            if team_tag and rank_tag:
                count += 1
                rank = rank_tag.text.strip()
                team_name = team_tag.get_text().strip()
                win_rate = (
                    win_rate_tag.text.strip() if win_rate_tag else "-"
                )

                ranking_list.append(
                    f"{rank}위: {team_name} (승률: {win_rate})"
                )

            if count == 10:
                break

        ranking_list.append("-------------------------")
        ranking_list.append("※ 다음 스포츠(Daum) 실시간 크롤링 완료")

        if count == 0:
            raise Exception("데이터 파싱 실패")

        final_ranking_text = "\n".join(ranking_list)

    except requests.exceptions.Timeout:
        final_ranking_text = "⚠️ 다음 스포츠 서버의 응답이 너무 늦어 순위를 가져오지 못했습니다. 대기 시간을 늘렸으니 잠시 후 다시 시도해 주세요!"
    except Exception as e:
        final_ranking_text = (
            f"⚠️ 실시간 순위를 가져오는 중 오류가 발생했습니다.\n오류 내용: {str(e)}"
        )

    response_body = {
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": final_ranking_text}}]
        },
    }
    return jsonify(response_body)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
