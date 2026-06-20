import os
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# 유저들의 선택 팀을 임시 저장할 딕셔너리 (메모리 저장 방식)
USER_TEAMS = {}

# 1. 팀 등록 API (예: 롯데 자이언츠, 삼성 등)
@app.route("/register-team", methods=["POST"])
def register_team():
    req = request.get_json()
    user_id = req.get("userRequest", {}).get("user", {}).get("id", "default_user")
    utterance = req.get("userRequest", {}).get("utterance", "").strip()
    
    # 입력된 텍스트에서 팀명만 정제 (예: "롯데 자이언츠" -> "롯데")
    team_name = utterance.split()[0] if utterance else "롯데"
    USER_TEAMS[user_id] = team_name

    return jsonify({
        "version": "2.0",
        "template": {
            "outputs": [{
                "simpleText": {
                    "text": f"🎉 [{team_name}] 등록 완료!\n실시간 순위와 경기 정보를 확인해보세요."
                }
            }]
        }
    })

# 2. 초고속 실시간 순위 조회 API (팀명만 노출)
@app.route("/show-ranking", methods=["POST"])
def show_ranking():
    url = "https://api-gw.sports.naver.com/kbaseball/category/record/team?seasonCode=2026"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=3)
        if response.status_code != 200:
            raise Exception("네이버 API 서버 응답 실패")

        data = response.json()
        teams = data.get("result", {}).get("regularSeason", {}).get("teamRecordList", [])

        if not teams:
            return jsonify({"version": "2.0", "template": {"outputs": [{"simpleText": {"text": "⚠️ 현재 조회 가능한 KBO 순위 데이터가 없습니다."}}]}})

        ranking_list = ["🏆 2026 KBO 프로야구 실시간 순위", "-------------------------"]
        for team in teams:
            rank = team.get("rank", "-")
            name = team.get("teamName", "-")
            ranking_list.append(f"{rank}위: {name}")

        ranking_list.append("-------------------------")
        ranking_list.append("※ 네이버 스포츠 실시간 API 반영 완료")
        final_text = "\n".join(ranking_list)

    except Exception as e:
        final_text = f"⚠️ 순위 조회 중 오류가 발생했습니다.\n원인: {str(e)}"

    return jsonify({
        "version": "2.0",
        "template": {"outputs": [{"simpleText": {"text": final_text}}]}
    })

# 3. 등록한 마이팀 경기 일정 조회 API (선발투수 정보 완벽 파싱)
@app.route("/show-match", methods=["POST"])
def show_match():
    req = request.get_json()
    user_id = req.get("userRequest", {}).get("user", {}).get("id", "default_user")
    
    # 등록된 팀이 없다면 기본값 '삼성'으로 설정
    my_team = USER_TEAMS.get(user_id, "삼성")
    
    # 2026년 오늘 날짜 기반으로 네이버 경기 일정 API 호출
    url = "https://api-gw.sports.naver.com/kbaseball/schedule/today?gameDateTime=2026-06-19"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=3)
        if response.status_code != 200:
            raise Exception("네이버 일정 API 응답 실패")

        data = response.json()
        games = data.get("result", {}).get("todayGames", [])
        
        target_game = None
        for game in games:
            if my_team in game.get("homeTeamName", "") or my_team in game.get("awayTeamName", ""):
                target_game = game
                break

        if not target_game:
            return jsonify({
                "version": "2.0",
                "template": {"outputs": [{"simpleText": {"text": f"📅 오늘 [{my_team}]의 경기 일정은 없습니다. (내 팀 휴식일)"}}]}
            })

        # 데이터 가공
        date = target_game.get("gameDate", "2026-06-19")
        time = target_game.get("gameTime", "18:30")
        home = target_game.get("homeTeamName", "홈")
        away = target_game.get("awayTeamName", "원정")
        
        # 선발 투수 정보 가져오기 (데이터가 없으면 '발표전' 처리)
        home_pitcher = target_game.get("homeLeftPitcherName") or target_game.get("homePitcherName") or "선발투수 발표전"
        away_pitcher = target_game.get("awayLeftPitcherName") or target_game.get("awayPitcherName") or "선발투수 발표전"

        match_text = (
            f"⭐ 내가 등록한 팀 [{my_team}] 경기 정보\n\n"
            f"📅 날짜: {date}\n"
            f"⏰ 시간: {time}\n"
            f"⚾ {away}({away_pitcher}) vs {home}({home_pitcher})\n\n"
            f"※ 네이버 실시간 데이터 동기화 완료"
        )

    except Exception as e:
        match_text = f"⚠️ 경기 정보를 가져오지 못했습니다.\n원인: {str(e)}"

    return jsonify({
        "version": "2.0",
        "template": {"outputs": [{"simpleText": {"text": match_text}}]}
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
