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
# ⚾ [크롤링 엔진] 다음 스포츠 KBO 실시간 선발 투수 필터링 함수
# -------------------------------------------------------------
def get_my_kbo_game(registered_team):
    """다음 스포츠에서 유저가 등록한 팀의 오늘 경기 데이터만 매칭하여 크롤링"""

    # 💡 [핵심 교정] 해외 서버(Render) 시간대 문제 해결!
    # UTC 시간에 9시간을 더해서 정확한 '한국 시간(KST)'을 구합니다.
    kst_now = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
    today_str = kst_now.strftime("%Y%m%d")  # 예: 20260618
    today_dash = kst_now.strftime("%Y-%m-%d")  # 예: 2026-06-18

    # 다음 스포츠 일정 주소로 접근
    url = f"https://sports.daum.net/schedule/kbo?date={today_str}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        # 타임아웃 7초로 연장
        response = requests.get(url, headers=headers, timeout=7)
        if response.status_code != 200:
            return "경기 일정을 불러올 수 없습니다. (포털 서버 응답 에러)"

        soup = BeautifulSoup(response.text, "html.parser")

        # 💡 매칭 확률을 높이기 위해 data-date 형식을 YYYYMMDD와 YYYY-MM-DD 둘 다 찾습니다.
        game_list = soup.find_all("li", {"data-date": today_str})
        if not game_list:
            game_list = soup.find_all("li", {"data-date": today_dash})

        # 만약 그래도 안 나오면 전체 li 태그 중 다음 구조를 가진 항목들을 싹 뒤집니다.
        if not game_list:
            game_list = soup.select(".list_schedule > li")

        if not game_list:
            return f"📅 [{today_dash}] 오늘 예정된 KBO 경기가 없습니다. (일정표 비어있음)"

        # 유저 팀 풀네임(예: "KT 위즈")에서 앞 2글자(예: "KT")만 추출
        short_team_name = registered_team.replace(" ", "")[:2]

        for game in game_list:
            try:
                # 원정팀(좌측) 이름 추출
                team_left_box = game.find("span", class_="team_left")
                if not team_left_box:
                    continue
                team_left_name = (
                    team_left_box.find("strong", class_="tit_team").text.strip()
                )

                # 홈팀(우측) 이름 추출
                team_right_box = game.find("span", class_="team_right")
                if not team_right_box:
                    continue
                team_right_strong = team_right_box.find(
                    "strong", class_="tit_team"
                )
                team_right_name = (
                    team_right_strong.text.replace("홈그라운드", "").strip()
                )

                # 💡 등록한 팀이 오늘 경기를 하는지 비교 검사
                if (short_team_name in team_left_name) or (
                    short_team_name in team_right_name
                ):
                    # 경기 시간 추출
                    time_tag = game.find("span", class_="info_time")
                    game_time = time_tag.text.strip() if time_tag else "18:30"

                    # 선발 투수 추출
                    pitcher_left_tag = team_left_box.find(
                        "span", class_="txt_team"
                    )
                    pitcher_left = (
                        pitcher_left_tag.text.strip()
                        if pitcher_left_tag
                        else "미정"
                    )

                    pitcher_right_tag = team_right_box.find(
                        "span", class_="txt_team"
                    )
                    pitcher_right = (
                        pitcher_right_tag.text.strip()
                        if pitcher_right_tag
                        else "미정"
                    )

                    result_text = f"⭐ 내가 등록한 팀 [{registered_team}] 경기 정보\n\n"
                    result_text += f"📅 날짜: {today_dash}\n"
                    result_text += f"⏰ 시간: {game_time}\n"
                    result_text += f"⚾ {team_left_name} ({pitcher_left}) vs {team_right_name} ({pitcher_right})\n\n"
                    result_text += "※ 다음 스포츠 실시간 데이터 반영 완료"
                    return result_text
            except Exception:
                continue  # 파싱 중 에러나는 빈 칸이나 다른 리그 요소는 패스

        return f"📅 오늘 [{registered_team}]의 경기 일정은 없습니다. (휴식일이거나 일정이 종료됨)"

    except requests.exceptions.Timeout:
        return "⚠️ 서버 연결 시간 초과로 경기 정보를 가져오지 못했습니다. 잠시 후 다시 시도해 주세요!"
    except Exception as e:
        return f"크롤링 중 에러가 발생했습니다: {str(e)}"


# -------------------------------------------------------------
# [스킬 1] 응원 팀 등록 주소 (/register-team)
# -------------------------------------------------------------
@app.route("/register-team", methods=["POST"])
def register_team():
    req = request.get_json()
    user_id = req["userRequest"]["user"]["id"]
    selected_team = req["action"]["clientExtra"]["team"]

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
            raise Exception("데이터 파싱 실패 (태그 구조 변경 가능성)")

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
