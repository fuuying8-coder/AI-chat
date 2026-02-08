# 一键部署到云服务器
# 用法: .\deploy-to-server.ps1 -ServerIP "你的服务器IP" -User "root"

param(
    [Parameter(Mandatory=$true)]
    [string]$ServerIP,
    
    [Parameter(Mandatory=$false)]
    [string]$User = "root"
)

Write-Host "📦 正在打包项目..." -ForegroundColor Green
tar -czf llm-chat.tar.gz --exclude=node_modules --exclude=.git --exclude=dist --exclude=__pycache__ .

Write-Host "📤 上传到服务器 $ServerIP..." -ForegroundColor Green
scp llm-chat.tar.gz ${User}@${ServerIP}:/tmp/

Write-Host "🚀 远程部署..." -ForegroundColor Green
ssh ${User}@${ServerIP} @"
    echo '解压项目...'
    mkdir -p /opt/llm-chat
    cd /opt/llm-chat
    tar -xzf /tmp/llm-chat.tar.gz
    rm /tmp/llm-chat.tar.gz
    
    echo '启动 Docker 容器...'
    docker compose down
    docker compose up -d --build
    
    echo '✅ 部署完成！'
    echo '访问地址：http://$(curl -s ifconfig.me):3001'
"@

Remove-Item llm-chat.tar.gz
Write-Host "✨ 全部完成！" -ForegroundColor Green
