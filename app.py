from flask import Flask, request, jsonify
import json
import os
import requests  # 외부 API 호출을 위해 추가
from openai import OpenAI  # OpenAI API 활용을 위해 추가

app = Flask(__name__)

# 사용자들의 응원 팀 데이터를 저장할 파일 경로
DB_FILE = 'user_teams.json'

# OpenAI API 클라이언트 설정
# Render의 Environment(환경변수)에 OPENAI_API_KEY를 등록하거나, 
# 테스트용이라면 직접 "sk-..." 키 값을 입력해도 됩니다.
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
    selected_team = req['action']['clientExtra']['team'] # 카카오톡 버튼에서 넘겨준 팀 이름
    
    user_data = load_data()
    user_data[user_id] = selected_team
    save_data(user_data)
    
    response_body = {
        "version": "2.0",
        "template": {
            "outputs": [
                {
                    "simpleText": {
                        "text": f"🎉 {selected_team} 등록이 완료되었습니다!\n앞으로 {selected_team}의 경기 정보를 우선적으로 알려드릴게요."
                    }
                }
            ]
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
    my_team = user_data.get(user_id) # 유저가 등록한 팀 가져오기
    
    # 예외 처리: 팀 등록을 안 한 경우
    if not my_team:
        return jsonify({
            "version": "2.0",
            "template": {
                "outputs": [{"simpleText": {"text": "아직 응원 팀이 등록되지 않았어요! 😅\n'팀 등록'을 먼저 진행해 주세요."}}]
            }
        })
    
    # 기본 경기 일정 정보 설정 (서버 텍스트 백업)
    raw_info = f"오늘 {my_team}의 경기는 18:30에 시작됩니다. 오늘의 선발 투수는 각 팀의 에이스 선수입니다!"
    
    # ChatGPT(OpenAI)에게 리포터/캐스터 말투 짬처리하기
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # 가볍고 응답 속도가 빠른 최적의 모델
            messages=[
                {"role": "system", "content": "너는 열정적이고 재치 있는 프로야구 캐스터야. 주어진 경기 정보를 바탕으로, 해당 팀 팬에게 신나고 친근한 카카오톡 이모티콘 말투로 2~3줄 요약해서 브리핑해줘."},
                {"role": "user", "content": raw_info}
            ],
            max_tokens=200
        )
        match_text = response.choices[0].message.content
    except Exception as e:
        # GPT API 오류나 타임아웃 발생 시 안전하게 기본 텍스트 출력
        match_text = f"📅 오늘 {my_team} 경기 안내\n\n{raw_info}\n\n※ 실시간 챗봇 서버 작동 중!"

    response_body = {
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": match_text}}]
        }
    }
    return jsonify(response_body)


# -------------------------------------------------------------
# [스킬 3] 현재 순위 조회 주소 (/show-ranking)
# -------------------------------------------------------------
@app.route('/show-ranking', methods=['POST'])
def show_ranking():
    try:
        # 1. 네이버 스포츠 실제 KBO 순위 데이터 가져오기 (실시간 반영)
        url = "https://m.sports.naver.com/kbaseball/record/kbo?seasonCode=2026&tab=teamRank"
        response = requests.get(url)
        raw_data = response.json()
        
        # 2. 데이터에서 팀명, 순위, 승률 추출하여 텍스트로 가공
        regular_team_record = raw_data.get('regularTeamRecordList', [])
        
        ranking_list = []
        for team in regular_team_record:
            rank = team.get('rank')
            name = team.get('teamName')
            win_rate = team.get('winRate')
            ranking_list.append(f"{rank}위: {name} (승률: {win_rate})")
            
        realtime_ranking_text = "\n".join(ranking_list)
        
        # 3. ChatGPT에게 실제 순위 데이터를 넘겨주고 이쁘게 정리하도록 짬처리하기
        gpt_response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "너는 KBO 프로야구 해설가야. 제공된 실시간 순위 리스트 데이터를 가독성이 좋고 깔끔하게 이모티콘을 섞어서 카카오톡 말풍선용 순위표로 만들어줘. 상위권 팀에겐 짧은 찬사를, 하위권 팀에겐 격려 멘트를 한 줄씩 덧붙여주면 좋아."},
                {"role": "user", "content": f"현재 실시간 KBO 순위 정보야:\n{realtime_ranking_text}"}
            ],
            max_tokens=400
        )
        final_ranking_text = gpt_response.choices[0].message.content

    except Exception as e:
        # 외부 API 장애나 오류 발생 시 예외 처리 안전장치
        final_ranking_text = "⚠️ 현재 실시간 야구 순위 데이터를 가져오는 데 실패했습니다. 잠시 후 다시 시도해 주세요!"

    response_body = {
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": final_ranking_text}}]
        }
    }
    return jsonify(response_body)


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
