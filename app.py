from flask import Flask, request, jsonify
import json
import os
import requests
from bs4 import BeautifulSoup  # 👈 크롤링을 위한 뷰티풀수프 라이브러리 추가

app = Flask(__name__)

DB_FILE = 'user_teams.json'

def load_data():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


# -------------------------------------------------------------
# [스킬 1] 응원 팀 등록 주소 (/register-team)
# -------------------------------------------------------------
@app.route('/register-team', methods=['POST'])
def register_team():
    req = request.get_json()
    user_id = req['userRequest']['user']['id']
    selected_team = req['action']['clientExtra']['team']
    
    user_data = load_data()
    user_data[user_id] = selected_team
    save_data(user_data)
    
    response_body = {
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": f"🎉 {selected_team} 등록이 완료되었습니다!\n앞으로 {selected_team}의 경기 정보와 실시간 순위를 알려드릴게요."}}]
        }
    }
    return jsonify(response_body)


# -------------------------------------------------------------
# [스킬 2] 오늘 경기 조회 주소 (/show-match)
# -------------------------------------------------------------
@app.route('/show-match', methods=['POST'])
def show_match():
    req = request.get_json()
    user_id = req['userRequest']['user']['id']
    
    user_data = load_data()
    my_team = user_data.get(user_id)
    
    if not my_team:
        return jsonify({"version": "2.0", "template": {"outputs": [{"simpleText": {"text": "아직 응원 팀이 등록되지 않았어요! 😅\n'팀 등록'을 먼저 진행해 주세요."}}]}})
    
    match_text = f"📅 오늘 {my_team} 경기 안내\n\n🔥 대진: {my_team} vs 상대팀\n⏰ 시간: 18:30\n⚾ 선발투수:\n- {my_team}: [홈런왕]\n- 상대팀: [삼진왕]\n\n※ 실시간 데이터 연동 테스트 중입니다."
    return jsonify({"version": "2.0", "template": {"outputs": [{"simpleText": {"text": match_text}}]}})


# -------------------------------------------------------------
# ⚾ [스킬 3] 다음 스포츠 HTML 맞춤형 실시간 순위 (/show-ranking)
# -------------------------------------------------------------
@app.route('/show-ranking', methods=['POST'])
def show_ranking():
    try:
        # 1. 다음 스포츠 KBO 순위 페이지 HTML 가져오기
        url = "https://sports.daum.net/record/KBO"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=3)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 2. 제공된 HTML 구조 분석 기반 타겟팅
        # '종합 순위' 타이틀 바로 아래에 있는 첫 번째 tbl_record 테이블의 tbody 행들을 가져옵니다.
        table_rows = soup.select('.record_kbo .tbl_record tbody tr')

        ranking_list = ["🏆 2026 KBO 프로야구 실시간 순위", "-------------------------"]
        
        count = 0
        for row in table_rows:
            # 순위 텍스트 추출 (.td_rank)
            rank_tag = row.select_one('.td_rank')
            # 팀 이름 텍스트 추출 (.txt_name)
            team_tag = row.select_one('.txt_name')
            # 승률 데이터 추출 (data-field="rank" 속성을 가진 td 태그)
            win_rate_tag = row.select_one('td[data-field="rank"]')
            
            if team_tag and rank_tag:
                count += 1
                rank = rank_tag.text.strip()
                
                # 팀 이름 뒤에 붙는 불필요한 태그/공백 제거
                team_name = team_tag.get_text().strip()
                
                win_rate = win_rate_tag.text.strip() if win_rate_tag else "-"
                
                ranking_list.append(f"{rank}위: {team_name} (승률: {win_rate})")
            
            if count == 10:
                break
                
        ranking_list.append("-------------------------")
        ranking_list.append("※ 다음 스포츠(Daum) 실시간 크롤링 완료")
        
        if count == 0:
            raise Exception("데이터 파싱 실패")
            
        final_ranking_text = "\n".join(ranking_list)

    except Exception as e:
        final_ranking_text = "⚠️ 다음 스포츠 페이지 구조 변경 또는 서버 지연으로 인해 실시간 순위를 가져오지 못했습니다. 잠시 후 다시 시도해 주세요!"

    response_body = {
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": final_ranking_text}}]
        }
    }
    return jsonify(response_body)

import datetime
import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request

app = Flask(__name__)


def get_today_kbo_games():
    # 1. 오늘 날짜를 YYYYMMDD 형식으로 구하기 (예: 20260618)
    today_str = datetime.datetime.now().strftime("%Y%m%d")

    # 2. 다음 스포츠 KBO 일정 URL (날짜 파라미터 동적 추가)
    url = f"https://sports.daum.net/schedule/kbo?date={today_str}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            return "경기 일정을 불러올 수 없습니다. (응답 에러)"

        soup = BeautifulSoup(response.text, "html.parser")

        # 오늘 날짜(data-date)에 맞는 li 태그들을 모두 찾음
        game_list = soup.find_all("li", {"data-date": today_str})

        if not game_list:
            return f"📅 {today_str[:4]}-{today_str[4:6]}-{today_str[6:]}\n오늘 예정된 KBO 경기가 없습니다."

        result_text = f"📅 오늘의 KBO 경기 및 선발투수\n\n"

        for game in game_list:
            # 경기 시간 추출
            time_tag = game.find("span", class_="info_time")
            game_time = time_tag.text.strip() if time_tag else "18:30"

            # 왼쪽 팀 (원정) 정보 추출
            team_left_box = game.find("span", class_="team_left")
            team_left_name = (
                team_left_box.find("strong", class_="tit_team").text.strip()
            )
            # 선발 투수 이름 (txt_team 클래스)
            pitcher_left_tag = team_left_box.find("span", class_="txt_team")
            pitcher_left = (
                pitcher_left_tag.text.strip() if pitcher_left_tag else "미정"
            )

            # 오른쪽 팀 (홈) 정보 추출
            team_right_box = game.find("span", class_="team_right")
            # 홈그라운드 아이콘 텍스트를 지우고 순수 팀 이름만 추출
            team_right_strong = team_right_box.find("strong", class_="tit_team")
            if team_right_strong.find("span", class_="ico_home"):
                # "홈그라운드" 글자 제외하고 가져오기
                team_right_name = (
                    team_right_strong.text.replace("홈그라운드", "").strip()
                )
            else:
                team_right_name = team_right_strong.text.strip()

            pitcher_right_tag = team_right_box.find("span", class_="txt_team")
            pitcher_right = (
                pitcher_right_tag.text.strip() if pitcher_right_tag else "미정"
            )

            # 한 경기의 텍스트 포맷 완성
            result_text += f"⏰ {game_time}\n"
            result_text += f"⚾ {team_left_name} ({pitcher_left}) vs {team_right_name} ({pitcher_right})\n"
            result_text += f"-------------------------\n"

        return result_text.strip()

    except Exception as e:
        return f"크롤링 중 에러가 발생했습니다: {str(e)}"


# 카카오톡 챗봇이 '오늘 경기 조회' 버튼을 눌렀을 때 호출할 API 라우트
@app.route("/api/today-games", methods=["POST"])
def today_games_endpoint():
    # 크롤링 함수 호출해서 텍스트 받아오기
    games_info = get_today_kbo_games()

    # 카카오톡 스킬 응답 JSON 규격에 맞게 반환
    response_body = {
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": games_info}}],
            "quickReplies": [],  # 필요시 하단 알맹이 버튼 추가
        },
    }
    return jsonify(response_body)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
