#!/bin/bash
# 一键部署脚本

SERVER_IP="your-server-ip"
SERVER_USER="your-username"
REMOTE_PATH="/home/$SERVER_USER/llm-chat"

echo "📦 打包项目..."
tar --exclude=node_modules --exclude=.git --exclude=dist -czf llm-chat.tar.gz .

echo "📤 上传到服务器..."
scp llm-chat.tar.gz $SERVER_USER@$SERVER_IP:$REMOTE_PATH/

echo "🚀 远程部署..."
ssh $SERVER_USER@$SERVER_IP << 'EOF'
cd /home/$USER/llm-chat
tar -xzf llm-chat.tar.gz
docker compose down
docker compose up -d --build
echo "✅ 部署完成！访问 http://$(curl -s ifconfig.me):3001"
EOF

rm llm-chat.tar.gz
echo "✨ 完成！"
