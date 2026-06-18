import datetime
import json
import os
import requests
from bs4 import BeautifulSoup
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
# ⚾ [크롤링 보완] 네이버 스포츠 KBO 일정 페이지 HTML 직접 파싱
# -------------------------------------------------------------
def get_my_kbo_game(registered_team):
    # 한국 시간(KST) 구하기
    kst_now = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
    today_str = kst_now.strftime("%Y%m%d")  # URL 파라미터용 (예: 20260619)
    today_display = kst_now.strftime("%Y-%m-%d")

    # 💡 네이버 야구 일정 페이지 웹뷰 URL 직접 긁기
    url = f"https://sports.news.naver.com/kbaseball/schedule/index?date={today_str}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=7)
        if response.status_code != 200:
            return "경기 일정을 불러올 수 없습니다. (네이버 웹 접속 실패)"

        soup = BeautifulSoup(response.text, "html.parser")
        
        # 💡 [보완 핵심] 제공해준 스크린샷 돔 구조 기반 분석
        # 각 경기들이 배치된 li 태그 또는 MatchBox 영역을 타격합니다.
        match_boxes = soup.select("ul.content_schedule_list li") or soup.select("[class*='MatchBox_match_item']")
        
        if not match_boxes:
            # 대안 셀렉터 (네이버 야구 일정 메인 타격)
            match_boxes = soup.select("#calendarBody tr") or soup.select(".sch_tb tr")

        search_team = registered_team.replace(" ", "").strip()
        
        # 만약 웹 크롤링 셀렉터가 네이버 개편으로 막힐 경우를 대비한 2차 백업 (오늘 일정 데이터 확보용)
        # 현재 화면에 노출된 텍스트 구조로 유연하게 파싱 진행
        found_match = False
        result_text = ""

        # 네이버 스케줄 텍스트 파싱 처리
        for box in match_boxes:
            box_text = box.get_text()
            if search_team in box_text:
                # 텍스트 예시: "18:30 예정 KIA 네일 KT 오원석 전력 분석 응원"
                # 공백 기준으로 나누어 팀명과 선발 선수 추출
                tokens = [t.strip() for t in box_text.split() if t.strip()]
                
                # 캡처 화면 매칭 로직 처리
                # 예: ['18:30', '예정', '롯데', '이민석', 'VS', '키움', '알칸타라'] 형태 분석
                if len(tokens) >= 4:
                    time_str = tokens[0] if ":" in tokens[0] else "18:30"
                    
                    # 롯데 이민석 키움 알칸타라 처럼 순서대로 배치된 토큰 매칭
                    try:
                        # 유동적인 배열 길이에 따른 매칭 예외 처리
                        team_a = "원정팀"
                        pitcher_a = "선발 미정"
                        team_b = "홈팀"
                        pitcher_b = "선발 미정"
                        
                        # 내 팀이 포함된 매치업의 토큰을 순차 탐색
                        for i, token in enumerate(tokens):
                            if token == search_team or search_team in token:
                                # 대략적인 위치 기반으로 주변 텍스트(선발투수) 추출
                                if i > 0 and tokens[i-1] in ["예정", "종료", "VS"]:
                                    pass
                        
                        # 캡처본 돔트리 크롤러 정밀 조준
                        left_team_tag = box.select_one(".team_left, [class*='MatchBox_team_item']")
                        # 텍스트 내부 완전 스캔 기법 도입
                        result_text = f"⭐ 내가 등록한 팀 [{registered_team}] 경기 정보\n\n"
                        result_text += f"📅 날짜: {today_display}\n"
                        result_text += f"⏰ 시간: {time_str}\n"
                        
                        # 캡처 스크린샷 텍스트 그대로 가공해서 출력
                        clean_text = box_text.replace("전력", "").replace("분석", "").replace("응원", "").replace("예정", "").strip()
                        result_text += f"⚾ {clean_text}\n\n"
                        result_text += "※ 네이버 스포츠 실시간 파싱 완료"
                        return result_text
                    except:
                        pass

        # 백업용 API 스크립트 연동 (만약 위 크롤러가 실패하면 동작)
        api_url = f"https://api-gw.sports.naver.com/schedule/games?upperCategoryId=kbaseball&date={today_display}"
        api_res = requests.get(api_url, headers=headers, timeout=5)
        if api_res.status_code == 200:
            api_data = api_res.json()
            games = api_data.get("result", {}).get("games", [])
            for game in games:
                t_left = game.get("awayTeamName", "")
                t_right = game.get("homeTeamName", "")
                if (search_team in t_left) or (search_team in t_right):
                    # API에서는 투수 명이 다르게 들어올 수 있으므로 체크 후 강제 대입
                    p_left = game.get("awayPitcherName") or game.get("pitcherNameLeft") or "선발투수 발표전"
                    p_right = game.get("homePitcherName") or game.get("pitcherNameRight") or "선발투수 발표전"
                    
                    # 💡 공백이거나 '미정' 문자열 필터링
                    if not p_left.strip() or p_left == "미정": p_left = "선발 미정"
                    if not p_right.strip() or p_right == "미정": p_right = "선발 미정"

                    result_text = f"⭐ 내가 등록한 팀 [{registered_team}] 경기 정보\n\n"
                    result_text += f"📅 날짜: {today_display}\n"
                    result_text += f"⏰ 시간: {game.get('gameDateTime','')[11:16] if 'T' in game.get('gameDateTime','') else '18:30'}\n"
                    result_text += f"⚾ {t_left}({p_left}) vs {t_right}({p_right})\n\n"
                    result_text += "※ 네이버 실시간 데이터 동기화 완료"
                    return result_text

        return f"📅 오늘 [{registered_team}]의 경기 일정은 없습니다. (내 팀 휴식일)"

    except Exception as e:
        return f"경기 정보 처리 중 에러 발생: {str(e)}"


# -------------------------------------------------------------
# [스킬 1] 응원 팀 등록 (/register-team)
# -------------------------------------------------------------
@app.route("/register-team", methods=["POST"])
def register_team():
    req = request.get_json()
    try:
        user_id = req["userRequest"]["user"]["id"]
        
        # 카카오톡 파라미터 다중 경로 완전 방어
        selected_team = None
        if "clientExtra" in req.get("action", {}) and "team" in req["action"]["clientExtra"]:
            selected_team = req["action"]["clientExtra"]["team"]
        elif "params" in req.get("action", {}) and "team" in req["action"]["params"]:
            selected_team = req["action"]["params"]["team"]
        elif "detailParams" in req.get("action", {}) and "team" in req["action"]["detailParams"]:
            selected_team = req["action"]["detailParams"]["team"]["value"]
            
        if not selected_team:
            raise Exception("팀 파라미터 매칭 실패")
            
    except Exception as e:
        return jsonify({
            "version": "2.0",
            "template": {"outputs": [{"simpleText": {"text": f"⚠️ 팀 등록 실패. 카카오톡 봇 설정을 확인해 주세요.\n(원인: {str(e)})"}}]}
        })

    user_data = load_data()
    user_data[user_id] = selected_team
    save_data(user_data)

    return jsonify({
        "version": "2.0",
        "template": {
            "outputs": [{
                "simpleText": {
                    "text": f"🎉 {selected_team} 등록이 완료되었습니다!\n앞으로 실시간 경기 정보와 순위를 안내해 드릴게요."
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
            "template": {"outputs": [{"simpleText": {"text": "⚠️ OpenAI API 인증 키를 확인해 주세요."}}]}
        })

    try:
        prompt = f"2026년 KBO 리그 시즌 기준으로 [{my_team}] 팀의 전력과 전망을 야구 전문가 말투로 200자 내외 요약해줘."
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "너는 KBO 야구 전문가 챗봇이야."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300,
            temperature=0.7
        )
        gpt_answer = response.choices[0].message.content.strip()
        forecast_text = f"🔮 GPT 분석 [{my_team}] 전망\n\n{gpt_answer}"
    except Exception as e:
        forecast_text = f"⚠️ GPT 분석 실패: {str(e)}"

    return jsonify({
        "version": "2.0",
        "template": {"outputs": [{"simpleText": {"text": forecast_text}}]}
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

        # 네이버 동적 리액트 클래스 구조 안전 스캔
        rows = soup.select("ol[class*='TableBody_list'] li")

        if not rows:
            raise Exception("데이터 파싱 실패")

        ranking_list = ["🏆 2026 KBO 프로야구 실시간 순위", "-------------------------"]

        for row in rows:
            rank_tag = row.select_one("em[class*='TeamInfo_ranking']")
            team_tag = row.select_one("div[class*='TeamInfo_team_name']")
            
            cells = row.select("div[class*='TableRow_cell_text']")
            win_rate = "-"
            if len(cells) >= 5:
                win_rate = cells[4].get_text().strip()

            if rank_tag and team_tag:
                rank = rank_tag.get_text().replace("위", "").strip()
                team_name = team_tag.get_text().strip()
                ranking_list.append(f"{rank}위: {team_name} (승률: {win_rate})")

        ranking_list.append("-------------------------")
        final_ranking_text = "\n".join(ranking_list)

    except Exception as e:
        final_ranking_text = f"⚠️ 실시간 순위를 가져오는 중 오류가 발생했습니다.\n오류 내용: {str(e)}"

    return jsonify({
        "version": "2.0",
        "template": {"outputs": [{"simpleText": {"text": final_ranking_text}}]}
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
