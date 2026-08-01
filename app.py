"""
AWS Lambda + Flask 後端入口點
使用 aws-lambda-powertools APIGatewayRestResolver 封裝
"""

from flask import Flask, jsonify
from aws_lambda_powertools.event_handler import APIGatewayRestResolver

# 初始化 Flask App
flask_app = Flask(__name__)

# 初始化 Lambda Powertools Resolver
resolver = APIGatewayRestResolver()


# --- API 路由 ---

@resolver.get("/api/test")
def test_endpoint():
    """端到端連線測試用路由"""
    return {
        "status": "success",
        "message": "Flask on Lambda connects successfully!"
    }


# --- Lambda 入口點 ---

def lambda_handler(event, context):
    """AWS Lambda handler，將 API Gateway 事件交由 Resolver 處理"""
    return resolver.resolve(event, context)


# --- 本地開發模式 ---

# 將 Resolver 的路由同步註冊到 Flask，方便本地測試
@flask_app.route("/api/test", methods=["GET"])
def local_test_endpoint():
    return jsonify({
        "status": "success",
        "message": "Flask on Lambda connects successfully!"
    })


if __name__ == "__main__":
    flask_app.run(debug=True, port=5000)
