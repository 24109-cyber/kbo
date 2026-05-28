from flask import Flask, request, jsonify
import json
import os

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
    # 원래는 크롤링을 해야 하지만, 발표 및 테스트를 위해 작동 가능한 샘플 데이터를 보여줍니다.
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
    # [수행평가용 테스트 데이터] 프로야구 가상 순위표
    ranking_text = "🏆 2026 KBO 프로야구 현재 순위\n" \
                   "-------------------------\n" \
                   "1위: KIA 타이거즈\n" \
                   "2위: 삼성 라이온즈\n" \
                   "3위: LG 트윈스\n" \
                   "4위: 두산 베어스\n" \
                   "5위: SSG 랜더스\n" \
                   "6위: 한화 이글스\n" \
                   "7위: KT 위즈\n" \
                   "8위: 롯데 자이언츠\n" \
                   "9위: NC 다이노스\n" \
                   "10위: 키움 히어로즈\n" \
                   "-------------------------\n" \
                   "※ 기준일: 오늘 자 순위표"

    response_body = {
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": ranking_text}}]
        }
    }
    return jsonify(response_body)


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
