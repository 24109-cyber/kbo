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
# ⚾ [정밀 스크래핑] 네이버 스포츠 KBO 일정 페이지 HTML 직접 조준 파싱
# -------------------------------------------------------------
def get_my_kbo_game(registered_team):
    # 한국 시간(KST) 구하기
    kst_now = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
    today_str = kst_now.strftime("%Y%m%d")  # 20260619 형식
    today_display = kst_now.strftime("%Y-%m-%d")

    # 네이버 야구 일정 페이지 PC 버전 URL
    url = f"https://sports.news.naver.com/kbaseball/schedule/index?date={today_str}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=7)
        if response.status_code != 200:
            return "경기 일정을 불러올 수 없습니다. (네이버 접속 실패)"

        soup = BeautifulSoup(response.text, "html.parser")
        
        # 💡 [핵심] 네이버 일정 테이블에서 오늘 경기 행(li)들을 전부 수집
        # 제공된 스크린샷 구조의 클래스 리스트 타격
        match_rows = soup.select("ul.content_schedule_list li") or soup.select("[class*='MatchBox_match_item']")
        
        # 만약 리액트 컴포넌트 내부 클래스가 숨겨져 있을 경우, 메인 캘린더 바디 타격
        if not match_rows:
            match_rows = soup.select("#calendarBody tr") or soup.select(".sch_tb tr")

        search_team = registered_team.replace(" ", "").strip()

        for row in match_rows:
            row_text = row.get_text()
            
            # 내가 등록한 팀이 이 경기 행에 포함되어 있다면!
            if search_team in row_text.replace(" ", ""):
                
                # 1. 경기 시간 파싱 (보통 맨 앞에 18:30 등으로 배치됨)
                time_str = "18:30"
                for token in row_text.split():
                    if ":" in token and len(token) <= 5:
                        time_str = token
                        break

                # 2. 좌측/우측 팀 정보 및 선발 투수 텍스트 추출 정밀화
                # 클래스 난수를 회피하기 위해 span 및 div 내부 텍스트 노드를 스캔
                teams_and_pitchers = []
                
                # 팀명과 투수명이 묶여있는 태그나 일반 텍스트 내에서 이름 쌍 찾기
                # 스크린샷 구조: [KIA 네일], [KT 오원석], [삼성 후라도], [한화 박준영]
                # row 내부의 텍스트 노드 중 2글자(팀명) + 이름(투수명) 조합을 정규 필터링
                words = [w.strip() for w in row_text.split() if w.strip()]
                
                # '예정', '전력', '분석', '응원', 'VS', 'V', 'S', time_str 제거하여 순수 데이터만 추출
                clean_words = []
                for w in words:
                    if w in ["예정", "종료", "전력", "분석", "응원", "VS", "경기", "취소", time_str]:
                        continue
                    # 💡 홈/원정 표시 글자 떼기
                    w_clean = w.replace("홈", "").strip()
                    if w_clean:
                        clean_words.append(w_clean)

                # clean_words 예시: ['롯데', '이민석', '키움', '알칸타라'] 또는 ['삼성', '후라도', '한화', '박준영']
                if len(clean_words) >= 4:
                    away_team = clean_words[0]
                    away_pitcher = clean_words[1]
                    home_team = clean_words[2]
                    home_pitcher = clean_words[3]
                else:
                    # 토큰 분리가 불 명확할 경우 텍스트 영역 직접 파싱 시도 (백업 가공)
                    # 텍스트 전체에서 선발 투수 명이 매칭되도록 강제 설정
                    away_team = "원정"
                    away_pitcher = "선발 미정"
                    home_team = "홈"
                    home_pitcher = "선발 미정"
                    
                    # 수동 파싱 보완
                    all_spans = [s.get_text().strip() for s in row.select("span") if s.get_text().strip()]
                    if len(all_spans) >= 4:
                        away_team, away_pitcher, home_team, home_pitcher = TensorMatch(all_spans)

                # 최종 문자열 조립
                result_text = f"⭐ 내가 등록한 팀 [{registered_team}] 경기 정보\n\n"
                result_text += f"📅 날짜: {today_display}\n"
                result_text += f"⏰ 시간: {time_str}\n"
                result_text += f"⚾ {away_team}({away_pitcher}) vs {home_team}({home_pitcher})\n\n"
                result_text += "※ 네이버 스포츠 화면 스크래핑 성공"
                return result_text

        return f"📅 오늘 [{registered_team}]의 경기 일정은 없습니다. (내 팀 휴식일)"

    except Exception as e:
        return f"경기 정보 파싱 오류 발생: {str(e)}"

def TensorMatch(span_list):
    # 유용 텍스트 추출 헬퍼 함수
    res = []
    for s in span_list:
        if s not in ["예정","전력","분석","응원","VS","","홈"]:
            res.append(s)
    if len(res) >= 4:
        return res[0], res[1], res[2], res[3]
    return "원정", "선발 미정", "홈", "선발 미정"


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
        elif "detailParams" in req.get("action", {}) and "team" in req["action"]["detailParams"]:
            selected_team = req["action"]["detailParams"]["team"]["value"]
            
        if not selected_team:
            raise Exception("팀 파라미터가 비어있습니다.")
            
    except Exception as e:
        return jsonify({
            "version": "2.0",
            "template": {"outputs": [{"simpleText": {"text": f"⚠️ 팀 등록 실패\n원인: {str(e)}"}}]}
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
            "template": {"outputs": [{"simpleText": {"text": "⚠️ OpenAI API 키가 설정되지 않았습니다."}}]}
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
        final_ranking_text = f"⚠️ 실시간 순위를 가져오는 중 오류가 발생했습니다.\n원인: {str(e)}"

    return jsonify({
        "version": "2.0",
        "template": {"outputs": [{"simpleText": {"text": final_ranking_text}}]}
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
