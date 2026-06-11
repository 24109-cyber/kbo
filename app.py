from flask import Flask, request, jsonify
import json
import os
import requests  # 실시간 순위를 가져오기 위해 사용

app = Flask(__name__)

# 사용자들의 응원 팀 데이터를 저장할 파일 경로
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
    
    # [수행평가용 테스트 데이터] 
    match_text = f"📅 오늘 {my_team} 경기 안내\n\n" \
                 f"🔥 대진: {my_team} vs 상대팀\n" \
                 f"⏰ 시간: 18:30\n" \
                 f"⚾ 선발투수:\n- {my_team}: [홈런왕]\n- 상대팀: [삼진왕]\n\n" \
                 f"※ 실시간 데이터 연동 테스트 중입니다."

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
        # 네이버 스포츠 실제 KBO 순위 데이터 가져오기 (실시간 반영, 3초 타임아웃 제한 설정)
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
        # 외부 API 장애나 5초 이내 타임아웃 발생 시 안전하게 튕겨내기
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
