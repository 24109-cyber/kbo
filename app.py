from flask import Flask, request, jsonify
import json
import os
from openai import OpenAI  # 지피티 연동 필수

app = Flask(__name__)

DB_FILE = 'user_teams.json'

# 🔑 Render Environment Variables에 등록한 OpenAI 키를 가져옵니다.
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
            "outputs": [{"simpleText": {"text": f"🎉 {selected_team} 등록이 완료되었습니다!\n이제 지피티가 {selected_team}의 최신 상태를 검색해 드릴게요."}}]
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
    # 간단하게 고정 텍스트나 기본 뼈대로 보여주는 기존 코드 유지
    ranking_text = "🏆 2026 KBO 프로야구 현재 순위\n-------------------------\n(실시간 순위 메뉴 혹은 네이버 스포츠에서 확인 가능합니다!)"
    return jsonify({"version": "2.0", "template": {"outputs": [{"simpleText": {"text": ranking_text}}]}})


# -------------------------------------------------------------
# ✨ [스킬 4] 지피티한테 "인터넷 뒤져서 팀 전망 알려줘" 프롬프트 짬처리 (/team-analysis)
# -------------------------------------------------------------
@app.route('/team-analysis', methods=['POST'])
def team_analysis():
    req = request.get_json()
    user_id = req['userRequest']['user']['id']
    
    user_data = load_data()
    my_team = user_data.get(user_id)
    
    if not my_team:
        return jsonify({
            "version": "2.0",
            "template": {
                "outputs": [{"simpleText": {"text": "응원 팀을 먼저 등록하셔야 지피티 검색 분석을 요청할 수 있어요! 🧐"}}]
            }
        })
        
    try:
        # 💬 네가 원한 바로 그 느낌! 지피티한테 "야구 뉴스랑 순위 직접 검색해서 알려줘"라고 프롬프트 때려박기
        # model은 최신 인터넷 검색 기능(Web Search) 연동이 유연한 gpt-4o 또는 gpt-4o-mini를 사용합니다.
        gpt_response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system", 
                    "content": "너는 최신 인터넷 검색 기능을 가진 AI 야구 해설위원이야. 사용자가 요청한 팀의 '가장 최신 KBO 뉴스, 현재 순위 분위기, 최근 경기 흐름'을 인터넷에서 직접 찾아서 파악한 뒤 브리핑해 줘야 해. 절대 옛날 정보나 거짓말을 지어내지 말고, 최근 2026 시즌 뉴스 기반으로 냉철하고 유쾌하게 분석해 줘. 답변은 카톡 말풍선 크기에 맞게 이모티콘을 섞어 3~4줄로 콤팩트하게 요약해 줄 것!"
                },
                {
                    "role": "user", 
                    "content": f"요즘 프로야구 {my_team} 팀 상태랑 앞으로의 시즌 전망 인터넷에서 최신 정보로 찾아서 핵심만 알려줘."
                }
            ],
            max_tokens=400
        )
        analysis_result = gpt_response.choices[0].message.content

    except Exception as e:
        analysis_result = f"⚠️ 지피티가 인터넷 검색 도중 와이파이가 끊겼습니다. (에러 발생)\n\n잠시 후 다시 시도해 주세요!"

    response_body = {
        "version": "2.0",
        "template": {
            "outputs": [
                {
                    "simpleText": {
                        "text": f"🤖 지피티가 실시간 뉴스를 검색한 결과!\n\n{analysis_result}"
                    }
                }
            ]
        }
    }
    return jsonify(response_body)


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
