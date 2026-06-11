from flask import Flask, request, jsonify
import json
import os
import requests
from openai import OpenAI  # 지피티 연동을 위해 필요!

app = Flask(__name__)

DB_FILE = 'user_teams.json'

# 🔑 Render Environment Variables에 등록한 OpenAI 키를 자동으로 가져옵니다.
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

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
            "outputs": [{"simpleText": {"text": f"🎉 {selected_team} 등록이 완료되었습니다!\n앞으로 {selected_team}의 정보를 분석해 드릴게요."}}]
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
# [스킬 3] 현재 순위 조회 주소 (/show-ranking)
# -------------------------------------------------------------
@app.route('/show-ranking', methods=['POST'])
def show_ranking():
    try:
        url = "https://sports.news.naver.com/kbaseball/v1/record/team?year=2026"
        response = requests.get(url, timeout=3)
        raw_data = response.json()
        
        regular_team_record = raw_data.get('regularTeamRecordList', [])
        ranking_list = ["🏆 2026 KBO 프로야구 실시간 순위", "-------------------------"]
        for team in regular_team_record:
            rank = team.get('rank')
            name = team.get('teamName')
            win_rate = team.get('winRate')
            ranking_list.append(f"{rank}위: {name} (승률: {win_rate})")
        ranking_list.append("-------------------------")
        ranking_list.append("※ 네이버 스포츠 실시간 데이터 연동 완료")
        final_ranking_text = "\n".join(ranking_list)
    except Exception as e:
        final_ranking_text = "⚠️ 현재 실시간 야구 순위 데이터를 가져오는 데 실패했습니다."

    return jsonify({"version": "2.0", "template": {"outputs": [{"simpleText": {"text": final_ranking_text}}]}})


# -------------------------------------------------------------
# ✨ [신규 스킬 4] 지피티의 팀 상태 분석 및 전망 (/team-analysis)
# -------------------------------------------------------------
@app.route('/team-analysis', methods=['POST'])
def team_analysis():
    req = request.get_json()
    user_id = req['userRequest']['user']['id']
    
    user_data = load_data()
    my_team = user_data.get(user_id)
    
    # 예외 처리: 팀 등록을 안 한 경우
    if not my_team:
        return jsonify({
            "version": "2.0",
            "template": {
                "outputs": [{"simpleText": {"text": "응원 팀을 먼저 등록하셔야 지피티 전문가의 정밀 분석을 받을 수 있어요! 🧐"}}]
            }
        })
        
    try:
        # 1. 실시간 순위표 데이터를 먼저 긁어옵니다. (지피티에게 힌트로 제공하기 위함)
        url = "https://sports.news.naver.com/kbaseball/v1/record/team?year=2026"
        response = requests.get(url, timeout=3)
        raw_data = response.json()
        regular_team_record = raw_data.get('regularTeamRecordList', [])
        
        # 2. 내 팀의 현재 순위와 승률 정보를 쏙 골라냅니다.
        my_team_info = "순위 정보 없음"
        for team in regular_team_record:
            if my_team in team.get('teamName'):
                my_team_info = f"현재 순위: {team.get('rank')}위, 승률: {team.get('winRate')}, 최근 10경기 성적: {team.get('recentMatches')}"
                break

        # 3. ✨ 지피티 짬처리: 진짜 야구 전문가처럼 연기하면서 분석 글 쓰게 만들기
        gpt_response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system", 
                    "content": "너는 대한민국 최고의 2026 KBO 프로야구 전문 분석가이자 해설위원이야. 제공된 팀의 현재 성적 데이터를 기반으로, 냉철하면서도 유쾌하게 해당 팀의 '요즘 팀 상태'와 '앞으로의 전망(가을야구 진출 가능성 등)'을 분석해 줘야 해. 말투는 친근한 카카오톡 해설가 말투로 이모티콘을 섞어서 3~4줄 내외로 깔끔하게 요약해 줘."
                },
                {
                    "role": "user", 
                    "content": f"분석할 팀: {my_team}\n해당 팀의 현재 성적: {my_team_info}"
                }
            ],
            max_tokens=400
        )
        analysis_result = gpt_response.choices[0].message.content

    except Exception as e:
        # 에러 발생 시 안내문
        analysis_result = f"⚠️ 지피티 해설위원이 분석 도중 대기실로 실려 갔습니다. (에러 발생)\n\n기본 정보: 현재 {my_team}의 분석 데이터를 처리할 수 없습니다. 잠시 후 다시 시도해 주세요!"

    response_body = {
        "version": "2.0",
        "template": {
            "outputs": [
                {
                    "simpleText": {
                        "text": f"🤖 지피티 야구 전문가의 팩트 체크!\n\n{analysis_result}"
                    }
                }
            ]
        }
    }
    return jsonify(response_body)


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
